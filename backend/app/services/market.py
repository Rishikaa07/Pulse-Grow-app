"""Market service.

One cached snapshot of the whole universe serves every user. A watchlist of 12
symbols does not trigger 12 provider calls, and 500 users watching NVDA do not
trigger 500 — they all read the same cache entry, refreshed on a fixed interval
by the background loop.

Benchmarks are built here too. A sector "index" is a capitalisation-weighted
price index over that sector's constituents, so "outperformed semiconductors by
3.1%" is a number we computed, not a label we invented.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..cache import cache
from ..config import settings
from ..providers import synthetic, universe
from ..providers.base import HistoryPoint, Quote, RawEvent
from ..providers.mock import MirrorProvider, SyntheticProvider, market_state
from ..providers.registry import Discrepancy, ProviderRegistry, QuoteBatch

log = logging.getLogger(__name__)

MARKET_INDEX_KEY = "^MARKET"
#: No single constituent may exceed this share of an index.
MAX_INDEX_WEIGHT = 0.22


def sector_index_key(sector_code: str) -> str:
    return f"^SECTOR_{sector_code}"


registry = ProviderRegistry([SyntheticProvider(market_state), MirrorProvider(market_state)])


@dataclass
class IndexLevel:
    key: str
    label: str
    level: float
    prev_level: float

    @property
    def change_today_pct(self) -> float:
        if self.prev_level <= 0:
            return 0.0
        return (self.level / self.prev_level - 1) * 100


@dataclass
class MarketSnapshotView:
    """Everything the rest of the app needs about "right now"."""

    quotes: dict[str, Quote]
    indices: dict[str, IndexLevel]
    events: list[RawEvent]
    discrepancies: list[Discrepancy] = field(default_factory=list)
    provider_health: list = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    degraded: bool = False
    captured_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def worst_freshness(self) -> str:
        order = ["fresh", "delayed", "stale", "unavailable"]
        worst = "fresh"
        for quote in self.quotes.values():
            if order.index(quote.quality.freshness) > order.index(worst):
                worst = quote.quality.freshness
        return worst

    def index_change(self, key: str) -> float | None:
        idx = self.indices.get(key)
        return idx.change_today_pct if idx else None


class MarketService:
    """Reads the tape. Holds no user state."""

    def __init__(self, registry_: ProviderRegistry | None = None) -> None:
        self.registry = registry_ or registry

    # -- snapshot -------------------------------------------------------------

    def snapshot(self, force: bool = False) -> MarketSnapshotView:
        key = (
            f"snapshot:{market_state.scenario}:{market_state.anchor_minute}"
            f":{market_state.primary_outage}:{market_state.secondary_outage}"
        )
        if not force:
            cached = cache.get(key)
            if cached is not None:
                return cached

        batch = self.registry.get_quotes(list(universe.ALL_SYMBOLS))
        view = MarketSnapshotView(
            quotes=batch.quotes,
            indices=self._build_indices(batch),
            events=self.registry.get_events(list(universe.ALL_SYMBOLS)),
            discrepancies=batch.discrepancies,
            provider_health=batch.provider_health,
            missing=batch.missing,
            degraded=batch.degraded,
        )
        cache.set(key, view, settings.quote_cache_ttl_s)
        return view

    def invalidate(self) -> None:
        cache.delete_prefix("snapshot:")

    @staticmethod
    def _build_indices(batch: QuoteBatch) -> dict[str, IndexLevel]:
        """Capitalisation-weighted price indices, rebased to 100.

        Constituent weights are capped at `MAX_INDEX_WEIGHT`, the same way real
        capped indices work. Without it a single mega-cap *is* its sector, and
        "outperformed semiconductors" would mostly mean "outperformed itself".
        """
        indices: dict[str, IndexLevel] = {}
        groups: dict[str, list[str]] = {MARKET_INDEX_KEY: []}
        for symbol in batch.quotes:
            inst = universe.get(symbol)
            if inst is None:
                continue
            groups.setdefault(sector_index_key(inst.sector), []).append(symbol)
            groups[MARKET_INDEX_KEY].append(symbol)

        for key, symbols in groups.items():
            raw = {
                s: inst.market_cap_b
                for s in symbols
                if (inst := universe.get(s)) is not None and inst.base_price > 0
            }
            total = sum(raw.values())
            cap = total * MAX_INDEX_WEIGHT if total > 0 else 0.0
            weights = {s: min(w, cap) for s, w in raw.items()} if cap > 0 else raw

            weight_sum = 0.0
            level = 0.0
            prev = 0.0
            for symbol, w in weights.items():
                inst = universe.get(symbol)
                quote = batch.quotes.get(symbol)
                if inst is None or quote is None:
                    continue
                weight_sum += w
                level += w * (quote.price / inst.base_price)
                prev += w * (quote.prev_close / inst.base_price)
            if weight_sum <= 0:
                continue
            label = (
                universe.MARKET_INDEX_NAME
                if key == MARKET_INDEX_KEY
                else universe.sector_label(key.replace("^SECTOR_", ""))
            )
            indices[key] = IndexLevel(
                key=key,
                label=label,
                level=round(100 * level / weight_sum, 6),
                prev_level=round(100 * prev / weight_sum, 6),
            )
        return indices

    # -- per-symbol -----------------------------------------------------------

    def history(self, symbol: str, days: int = 90) -> list[HistoryPoint]:
        key = f"history:{symbol.upper()}:{days}:{datetime.now(UTC).date()}"
        cached = cache.get(key)
        if cached is not None:
            return cached
        points = self.registry.get_history(symbol.upper(), days)
        if points:
            cache.set(key, points, settings.history_cache_ttl_s)
        return points

    @staticmethod
    def stats(symbol: str) -> dict[str, float]:
        return synthetic.history_stats(symbol.upper(), datetime.now(UTC).date())

    @staticmethod
    def expected_volume_fraction(now: datetime | None = None) -> float:
        return synthetic.expected_volume_fraction(now or datetime.now(UTC))

    def health(self) -> list:
        return self.registry.health()


market_service = MarketService()
