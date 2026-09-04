"""Overview service — the orchestration layer behind the main screen.

Responsibilities, in order:

1.  Work out which visit this is, and therefore what the user last actually saw.
2.  Score every watched symbol against that baseline.
3.  Write the material changes into the inbox, idempotently.
4.  Record what the user is seeing now, so the *next* visit has a baseline.
5.  Return a ranked, grouped view plus an honest account of data quality.

Step 4 happens last and writes into the *current* visit, never the previous one,
which is what keeps the baseline stable across refreshes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from ..config import settings
from ..db.models import User, Watchlist
from ..domain.attention.engine import AttentionEngine
from ..domain.attention.types import (
    AttentionInput,
    AttentionResult,
    Baseline,
    EventInput,
    MarketContext,
    Severity,
)
from ..domain.attention.weights import AttentionWeights
from ..providers import universe
from ..repositories.events import (
    STATUS_NEW,
    ChangeEventRepository,
    DataQualityRepository,
)
from ..repositories.snapshots import VisitRepository
from ..repositories.watchlists import WatchlistRepository
from .market import MARKET_INDEX_KEY, MarketService, MarketSnapshotView, market_service, sector_index_key

log = logging.getLogger(__name__)

#: Only these land in the inbox. Everything quieter stays in the live view.
INBOX_SEVERITIES = {Severity.HIGH, Severity.MEDIUM}


@dataclass
class VisitContext:
    started_at: datetime
    is_new_visit: bool
    last_visit_at: datetime | None
    away_seconds: float | None
    baseline_source: str


@dataclass
class OverviewSummary:
    tracked: int
    meaningful_changes: int
    unusual_moves: int
    events: int
    quiet: int
    new_in_inbox: int


@dataclass
class ScoredItem:
    result: AttentionResult
    sector_code: str
    sector_label: str
    status: str
    change_event_id: int | None


@dataclass
class Overview:
    watchlist: Watchlist
    visit: VisitContext
    summary: OverviewSummary
    items: list[ScoredItem]
    snapshot: MarketSnapshotView
    generated_at: datetime


class OverviewService:
    def __init__(self, db: Session, market: MarketService | None = None) -> None:
        self.db = db
        self.market = market or market_service
        self.watchlists = WatchlistRepository(db)
        self.visits = VisitRepository(db)
        self.events = ChangeEventRepository(db)
        self.quality = DataQualityRepository(db)

    # -- public ---------------------------------------------------------------

    def build(self, user: User, watchlist: Watchlist) -> Overview:
        now = datetime.now(UTC)
        symbols = [item.symbol for item in sorted(watchlist.items, key=lambda i: i.position)]
        snapshot = self.market.snapshot()
        self._log_quality(snapshot)

        visit, previous, is_new_visit = self.visits.current_or_new(
            user.id, watchlist.id, settings.visit_idle_timeout_s, now
        )
        baseline_rows = self.visits.observations(previous.id) if previous else {}
        last_visit_at = _aware(previous.last_seen_at) if previous else None
        away = (now - last_visit_at).total_seconds() if last_visit_at else None

        engine = AttentionEngine(AttentionWeights.from_dict(user.attention_profile))
        expected_fraction = self.market.expected_volume_fraction(now)

        scored: list[ScoredItem] = []
        for symbol in symbols:
            inst = universe.get(symbol)
            quote = snapshot.quotes.get(symbol)
            if inst is None or quote is None:
                continue
            data = self._build_input(
                inst, quote, snapshot, baseline_rows, expected_fraction, now
            )
            result = engine.score(data)
            scored.append(
                ScoredItem(
                    result=result,
                    sector_code=inst.sector,
                    sector_label=universe.sector_label(inst.sector),
                    status=STATUS_NEW,
                    change_event_id=None,
                )
            )

        scored.sort(key=lambda s: (-s.result.attention_score, s.result.symbol))
        self._persist_changes(user, watchlist, scored)
        self._record_observations(user, watchlist, visit, snapshot, symbols, now)

        summary = self._summarise(scored, watchlist.id)
        baseline_source = (
            "last_visit" if baseline_rows else ("session_open" if not previous else "partial")
        )

        return Overview(
            watchlist=watchlist,
            visit=VisitContext(
                started_at=_aware(visit.started_at),
                is_new_visit=is_new_visit,
                last_visit_at=last_visit_at,
                away_seconds=away,
                baseline_source=baseline_source,
            ),
            summary=summary,
            items=scored,
            snapshot=snapshot,
            generated_at=now,
        )

    # -- internals ------------------------------------------------------------

    def _build_input(
        self,
        inst: universe.Instrument,
        quote,
        snapshot: MarketSnapshotView,
        baseline_rows: dict,
        expected_fraction: float,
        now: datetime,
    ) -> AttentionInput:
        stats = self.market.stats(inst.symbol)

        row = baseline_rows.get(inst.symbol)
        if row is not None and row.price > 0:
            baseline = Baseline(
                price=row.price,
                volume=row.volume,
                observed_at=_aware(row.observed_at),
                source="last_visit",
            )
        else:
            # No previous observation: compare against today's open and label it,
            # rather than pretending a baseline exists.
            baseline = Baseline(
                price=quote.open_price,
                volume=None,
                observed_at=_start_of_session(now),
                source="session_open",
            )

        context = MarketContext(
            sector_code=inst.sector,
            sector_label=universe.sector_label(inst.sector),
            sector_change_pct=self._benchmark_change(
                snapshot, sector_index_key(inst.sector), baseline_rows, baseline
            ),
            market_change_pct=self._benchmark_change(
                snapshot, MARKET_INDEX_KEY, baseline_rows, baseline
            ),
            beta=inst.beta,
        )

        events = [
            EventInput(e.id, e.headline, e.kind, e.occurred_at)
            for e in snapshot.events
            if e.symbol == inst.symbol
        ]

        return AttentionInput(
            symbol=inst.symbol,
            name=inst.name,
            price=quote.price,
            prev_close=quote.prev_close,
            open_price=quote.open_price,
            volume=quote.volume,
            as_of=_aware(quote.as_of),
            expected_volume_fraction=expected_fraction,
            avg_volume_20d=stats.get("avg_volume_20d"),
            daily_sigma=stats.get("daily_sigma"),
            history_sample=int(stats.get("sample_size", 0)),
            week_ago_close=stats.get("week_ago_close"),
            baseline=baseline,
            context=context,
            events=events,
            freshness=quote.quality.freshness,
            data_age_seconds=quote.quality.age_seconds,
            has_conflict=quote.quality.has_conflict,
            discrepancy_pct=quote.quality.discrepancy_pct,
            quality_notes=list(quote.quality.notes),
        )

    @staticmethod
    def _benchmark_change(
        snapshot: MarketSnapshotView,
        index_key: str,
        baseline_rows: dict,
        baseline: Baseline,
    ) -> float | None:
        """Benchmark move measured over exactly the user's window.

        Index levels are snapshotted alongside prices during each visit, so the
        comparison window for the stock and its benchmark is identical. Without
        a stored level we fall back to the benchmark's move on the day, which is
        the closest honest approximation.
        """
        index = snapshot.indices.get(index_key)
        if index is None:
            return None
        row = baseline_rows.get(index_key)
        if row is not None and row.price > 0 and baseline.source == "last_visit":
            return round((index.level / row.price - 1) * 100, 4)
        return round(index.change_today_pct, 4)

    def _persist_changes(
        self, user: User, watchlist: Watchlist, scored: list[ScoredItem]
    ) -> None:
        existing = {
            f"{e.symbol}:{e.fingerprint}": e for e in self.events.feed(watchlist.id, limit=500)
        }
        for item in scored:
            result = item.result
            key = f"{result.symbol}:{result.fingerprint}"
            known = existing.get(key)

            if result.severity not in INBOX_SEVERITIES:
                # Not inbox-worthy. If we have seen this exact change before,
                # keep its status so the UI stays consistent.
                item.status = known.status if known else STATUS_NEW
                item.change_event_id = known.id if known else None
                continue

            event, _created = self.events.upsert(
                user_id=user.id,
                watchlist_id=watchlist.id,
                symbol=result.symbol,
                fingerprint=result.fingerprint,
                attention_score=result.attention_score,
                severity=str(result.severity),
                headline=result.headline,
                explanation=result.explanation,
                signals=[
                    {
                        "type": str(s.type),
                        "value": s.value,
                        "display": s.display,
                        "weight": s.weight,
                        "contribution": s.contribution,
                        "detail": s.detail,
                    }
                    for s in result.signals
                    if s.is_material
                ],
                metrics={
                    "changeSinceVisitPct": result.change_since_visit_pct,
                    "changeTodayPct": result.change_today_pct,
                    "sectorChangePct": result.sector_change_pct,
                    "marketChangePct": result.market_change_pct,
                    "relativeEdgePct": result.relative_edge_pct,
                    "volumeRatio": result.volume_ratio,
                    "price": result.price,
                    "baselinePrice": result.baseline.price,
                },
                confidence=str(result.confidence.level),
            )
            if event is not None:
                item.status = event.status
                item.change_event_id = event.id

    def _record_observations(
        self,
        user: User,
        watchlist: Watchlist,
        visit,
        snapshot: MarketSnapshotView,
        symbols: list[str],
        now: datetime,
    ) -> None:
        observed: dict[str, tuple[float, int | None]] = {}
        for symbol in symbols:
            quote = snapshot.quotes.get(symbol)
            if quote is not None:
                observed[symbol] = (quote.price, quote.volume)
        # Index levels ride along as pseudo-symbols so benchmark comparisons use
        # the same window as the stock, with no separate storage mechanism.
        for key, index in snapshot.indices.items():
            observed[key] = (index.level, None)
        if observed:
            self.visits.record_observations(visit, user.id, watchlist.id, observed, now)

    def _summarise(self, scored: list[ScoredItem], watchlist_id: int) -> OverviewSummary:
        meaningful = sum(1 for s in scored if s.result.severity is Severity.HIGH)
        unusual = sum(
            1
            for s in scored
            if (s.result.volume_ratio or 0) >= 1.8
            or (s.result.sigma_multiple or 0) >= 2.0
        )
        events = sum(1 for s in scored if s.result.events)
        quiet = sum(1 for s in scored if s.result.severity is Severity.NONE)
        return OverviewSummary(
            tracked=len(scored),
            meaningful_changes=meaningful,
            unusual_moves=unusual,
            events=events,
            quiet=quiet,
            new_in_inbox=self.events.count_new(watchlist_id),
        )

    def _log_quality(self, snapshot: MarketSnapshotView) -> None:
        for disc in snapshot.discrepancies:
            if self.quality.recent_within(300, "discrepancy", disc.symbol):
                continue
            self.quality.record(
                "discrepancy",
                (
                    f"{disc.symbol}: {disc.primary_source} {disc.primary_price} vs "
                    f"{disc.other_source} {disc.other_price} "
                    f"({disc.deviation_pct:.2f}%). Using {disc.primary_source}."
                ),
                symbol=disc.symbol,
                payload={
                    "deviationPct": disc.deviation_pct,
                    "selected": disc.primary_source,
                },
            )
        for health in snapshot.provider_health:
            if health.ok or self.quality.recent_within(300, "outage", None):
                continue
            self.quality.record(
                "outage", f"{health.name} unavailable: {health.detail}", payload={}
            )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _start_of_session(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
