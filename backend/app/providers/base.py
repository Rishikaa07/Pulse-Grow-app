"""Provider abstraction.

The rest of the application never talks to a feed directly. It asks the
`ProviderRegistry` for reconciled quotes, so swapping the synthetic feed for a
real vendor means writing one class and registering it — nothing else changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


class ProviderError(RuntimeError):
    """Base class for anything a feed can do to ruin your day."""


class ProviderTimeout(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class UnknownSymbol(ProviderError):
    pass


@dataclass(frozen=True)
class RawQuote:
    symbol: str
    price: float
    prev_close: float
    open_price: float
    day_high: float
    day_low: float
    volume: int
    as_of: datetime
    source: str


@dataclass(frozen=True)
class HistoryPoint:
    day: str
    close: float
    volume: int


@dataclass(frozen=True)
class RawEvent:
    id: str
    symbol: str
    headline: str
    kind: str
    occurred_at: datetime
    source: str


@dataclass(frozen=True)
class ProviderHealth:
    name: str
    priority: int
    ok: bool
    latency_ms: float
    detail: str = ""


class MarketDataProvider(ABC):
    """A source of market data. Implementations must be side-effect free."""

    #: Lower number wins when two providers disagree.
    priority: int = 100
    name: str = "provider"

    @abstractmethod
    def get_quotes(self, symbols: list[str]) -> dict[str, RawQuote]:
        """Return quotes for the symbols this provider can serve.

        Partial results are allowed and expected — the caller reconciles.
        """

    @abstractmethod
    def get_history(self, symbol: str, days: int) -> list[HistoryPoint]:
        ...

    def get_events(self, symbols: list[str]) -> list[RawEvent]:
        return []

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.name, self.priority, True, 0.0)


@dataclass
class QuoteQuality:
    """Everything we know about how much to trust a single quote."""

    freshness: str  # fresh | delayed | stale | unavailable
    age_seconds: float
    selected_source: str
    sources_agreeing: int = 1
    sources_total: int = 1
    discrepancy_pct: float | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def has_conflict(self) -> bool:
        return self.sources_total > 1 and self.sources_agreeing < self.sources_total


@dataclass(frozen=True)
class Quote:
    """A reconciled quote: the value plus its provenance."""

    symbol: str
    price: float
    prev_close: float
    open_price: float
    day_high: float
    day_low: float
    volume: int
    as_of: datetime
    quality: QuoteQuality
