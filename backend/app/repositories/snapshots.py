from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.models import MarketSnapshot, UserSnapshot, Visit


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class VisitRepository:
    """Owns the "since your last check" baseline.

    A visit is a continuous stretch of attention. Polling during a visit updates
    what you have *seen* but must not move the baseline you are being compared
    against — otherwise "since your last check" collapses to zero every time the
    page refreshes, which is the bug that makes most watchlists useless.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def current_or_new(
        self, user_id: int, watchlist_id: int, idle_timeout_s: int, now: datetime | None = None
    ) -> tuple[Visit, Visit | None, bool]:
        """Return (current visit, previous visit, is_new_visit).

        The previous visit's observations are the baseline for this one.
        """
        now = now or datetime.now(UTC)
        recent = list(
            self.db.scalars(
                select(Visit)
                .where(Visit.user_id == user_id, Visit.watchlist_id == watchlist_id)
                .order_by(Visit.last_seen_at.desc())
                .limit(2)
            )
        )

        if recent:
            latest = recent[0]
            idle = (now - _aware(latest.last_seen_at)).total_seconds()
            if not latest.closed and idle <= idle_timeout_s:
                latest.last_seen_at = now
                self.db.flush()
                previous = recent[1] if len(recent) > 1 else None
                return latest, previous, False
            latest.closed = True

        visit = Visit(
            user_id=user_id, watchlist_id=watchlist_id, started_at=now, last_seen_at=now
        )
        self.db.add(visit)
        self.db.flush()
        return visit, (recent[0] if recent else None), True

    def close_current(self, user_id: int, watchlist_id: int) -> None:
        """Used by "reset baseline": end the visit so the next load starts fresh."""
        self.db.execute(
            delete(Visit).where(
                Visit.user_id == user_id,
                Visit.watchlist_id == watchlist_id,
                Visit.closed.is_(False),
            )
        )
        self.db.flush()

    def observations(self, visit_id: int) -> dict[str, UserSnapshot]:
        rows = self.db.scalars(select(UserSnapshot).where(UserSnapshot.visit_id == visit_id))
        return {row.symbol: row for row in rows}

    def record_observations(
        self,
        visit: Visit,
        user_id: int,
        watchlist_id: int,
        observed: dict[str, tuple[float, int | None]],
        now: datetime | None = None,
    ) -> None:
        """Upsert what the user is seeing right now, inside this visit."""
        now = now or datetime.now(UTC)
        existing = self.observations(visit.id)
        for symbol, (price, volume) in observed.items():
            row = existing.get(symbol)
            if row is None:
                row = UserSnapshot(
                    visit_id=visit.id,
                    user_id=user_id,
                    watchlist_id=watchlist_id,
                    symbol=symbol,
                    price=price,
                    volume=volume,
                    observed_at=now,
                )
                self.db.add(row)
            else:
                row.price = price
                row.volume = volume
                row.observed_at = now
        try:
            self.db.flush()
        except IntegrityError:
            # Concurrent tabs can race the insert; the unique index wins and the
            # loser simply re-reads. Losing this race changes nothing observable.
            self.db.rollback()

    def prune_visits(self, older_than_days: int = 90) -> int:
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        result = self.db.execute(delete(Visit).where(Visit.last_seen_at < cutoff))
        return result.rowcount or 0


class MarketSnapshotRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def record_many(self, rows: list[dict]) -> None:
        self.db.add_all([MarketSnapshot(**row) for row in rows])
        self.db.flush()

    def latest(self, symbol: str) -> MarketSnapshot | None:
        return self.db.scalar(
            select(MarketSnapshot)
            .where(MarketSnapshot.symbol == symbol.upper())
            .order_by(MarketSnapshot.captured_at.desc())
            .limit(1)
        )

    def prune(self, older_than_hours: int = 48) -> int:
        cutoff = datetime.now(UTC) - timedelta(hours=older_than_hours)
        result = self.db.execute(
            delete(MarketSnapshot).where(MarketSnapshot.captured_at < cutoff)
        )
        return result.rowcount or 0
