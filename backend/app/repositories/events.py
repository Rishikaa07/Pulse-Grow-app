from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.models import ChangeEvent, DataQualityLog, EventReview

STATUS_NEW = "new"
STATUS_REVIEWED = "reviewed"
STATUS_DISMISSED = "dismissed"
VALID_STATUSES = {STATUS_NEW, STATUS_REVIEWED, STATUS_DISMISSED}


class ChangeEventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(self, **fields) -> tuple[ChangeEvent, bool]:
        """Insert a change unless this exact change is already in the inbox.

        Returns (event, created). Idempotency is enforced by the unique index on
        (watchlist_id, fingerprint) — the background loop and a user refresh can
        both attempt the write and exactly one row results.
        """
        watchlist_id = fields["watchlist_id"]
        fingerprint = fields["fingerprint"]
        existing = self.db.scalar(
            select(ChangeEvent).where(
                ChangeEvent.watchlist_id == watchlist_id,
                ChangeEvent.fingerprint == fingerprint,
            )
        )
        if existing is not None:
            # Refresh the live measurements but never resurrect a reviewed item.
            existing.attention_score = fields["attention_score"]
            existing.metrics = fields["metrics"]
            existing.signals = fields["signals"]
            existing.explanation = fields["explanation"]
            existing.confidence = fields["confidence"]
            self.db.flush()
            return existing, False

        event = ChangeEvent(**fields)
        self.db.add(event)
        try:
            self.db.flush()
        except IntegrityError:
            self.db.rollback()
            event = self.db.scalar(
                select(ChangeEvent).where(
                    ChangeEvent.watchlist_id == watchlist_id,
                    ChangeEvent.fingerprint == fingerprint,
                )
            )
            return event, False
        return event, True

    def feed(
        self, watchlist_id: int, statuses: set[str] | None = None, limit: int = 100
    ) -> list[ChangeEvent]:
        stmt = select(ChangeEvent).where(ChangeEvent.watchlist_id == watchlist_id)
        if statuses:
            stmt = stmt.where(ChangeEvent.status.in_(statuses))
        stmt = stmt.order_by(
            ChangeEvent.attention_score.desc(), ChangeEvent.detected_at.desc()
        ).limit(limit)
        return list(self.db.scalars(stmt))

    def by_symbol(self, watchlist_id: int, symbol: str, limit: int = 20) -> list[ChangeEvent]:
        stmt = (
            select(ChangeEvent)
            .where(ChangeEvent.watchlist_id == watchlist_id, ChangeEvent.symbol == symbol.upper())
            .order_by(ChangeEvent.detected_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def count_new(self, watchlist_id: int) -> int:
        return (
            self.db.scalar(
                select(func.count(ChangeEvent.id)).where(
                    ChangeEvent.watchlist_id == watchlist_id,
                    ChangeEvent.status == STATUS_NEW,
                )
            )
            or 0
        )

    def statuses_for(self, watchlist_id: int) -> dict[str, str]:
        """symbol -> most relevant current status, for decorating the live feed."""
        rows = self.db.execute(
            select(ChangeEvent.symbol, ChangeEvent.status, ChangeEvent.fingerprint).where(
                ChangeEvent.watchlist_id == watchlist_id
            )
        ).all()
        return {f"{symbol}:{fingerprint}": status for symbol, status, fingerprint in rows}

    def get_owned(self, user_id: int, event_id: int) -> ChangeEvent | None:
        return self.db.scalar(
            select(ChangeEvent).where(
                ChangeEvent.id == event_id, ChangeEvent.user_id == user_id
            )
        )

    def set_status(self, event: ChangeEvent, status: str, user_id: int) -> ChangeEvent:
        if status not in VALID_STATUSES:
            raise ValueError(f"unknown status {status!r}")
        if event.status == status:
            return event
        self.db.add(
            EventReview(
                change_event_id=event.id,
                user_id=user_id,
                from_status=event.status,
                to_status=status,
            )
        )
        event.status = status
        event.reviewed_at = datetime.now(UTC) if status != STATUS_NEW else None
        self.db.flush()
        return event

    def mark_all(self, watchlist_id: int, user_id: int, status: str = STATUS_REVIEWED) -> int:
        events = self.feed(watchlist_id, statuses={STATUS_NEW}, limit=500)
        for event in events:
            self.set_status(event, status, user_id)
        return len(events)

    def prune(self, older_than_days: int = 30) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        result = self.db.execute(delete(ChangeEvent).where(ChangeEvent.detected_at < cutoff))
        return result.rowcount or 0


class DataQualityRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record(self, kind: str, detail: str, symbol: str | None = None, payload: dict | None = None) -> None:
        self.db.add(
            DataQualityLog(kind=kind, detail=detail, symbol=symbol, payload=payload or {})
        )
        self.db.flush()

    def recent(self, limit: int = 25) -> list[DataQualityLog]:
        return list(
            self.db.scalars(
                select(DataQualityLog).order_by(DataQualityLog.detected_at.desc()).limit(limit)
            )
        )

    def recent_within(self, seconds: int, kind: str, symbol: str | None) -> bool:
        """Rate-limit identical quality logs so one flapping feed cannot spam."""
        cutoff = datetime.now(UTC) - timedelta(seconds=seconds)
        stmt = select(func.count(DataQualityLog.id)).where(
            DataQualityLog.kind == kind, DataQualityLog.detected_at >= cutoff
        )
        if symbol:
            stmt = stmt.where(DataQualityLog.symbol == symbol)
        return (self.db.scalar(stmt) or 0) > 0
