"""Domain types for the attention engine.

Deliberately plain dataclasses: the engine is pure, has no database or HTTP
imports, and can be unit-tested without a running application.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class SignalType(StrEnum):
    PRICE_MOVE = "PRICE_MOVE"
    VOLUME_ANOMALY = "VOLUME_ANOMALY"
    SECTOR_OUTPERFORMANCE = "SECTOR_OUTPERFORMANCE"
    MARKET_OUTPERFORMANCE = "MARKET_OUTPERFORMANCE"
    HISTORICAL_UNUSUALNESS = "HISTORICAL_UNUSUALNESS"
    EVENT = "EVENT"
    MISSED_WHILE_AWAY = "MISSED_WHILE_AWAY"


class Severity(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class Signal:
    type: SignalType
    #: Raw measured value, in the signal's own units (percent, multiple, sigma…).
    value: float
    #: Human-readable rendering of `value`, e.g. "2.4× normal".
    display: str
    #: Maximum points this signal can contribute under the active weights.
    weight: float
    #: Points it actually contributed.
    contribution: float
    #: One clause explaining what was measured, generated from the number.
    detail: str

    @property
    def is_material(self) -> bool:
        return self.contribution >= 1.0


@dataclass(frozen=True)
class Baseline:
    """What the user last actually saw."""

    price: float
    volume: int | None
    observed_at: datetime
    #: "last_visit" when we have a real observation, otherwise a labelled fallback.
    source: str


@dataclass(frozen=True)
class MarketContext:
    """Benchmarks measured over exactly the same window as the stock."""

    sector_code: str
    sector_label: str
    sector_change_pct: float | None
    market_change_pct: float | None
    beta: float = 1.0


@dataclass(frozen=True)
class EventInput:
    id: str
    headline: str
    kind: str
    occurred_at: datetime


@dataclass(frozen=True)
class AttentionInput:
    symbol: str
    name: str
    price: float
    prev_close: float
    open_price: float
    volume: int
    as_of: datetime
    #: Fraction of a normal session's volume expected to have traded by now.
    expected_volume_fraction: float
    avg_volume_20d: float | None
    daily_sigma: float | None
    history_sample: int
    week_ago_close: float | None
    baseline: Baseline
    context: MarketContext
    events: list[EventInput] = field(default_factory=list)
    freshness: str = "fresh"
    data_age_seconds: float = 0.0
    has_conflict: bool = False
    discrepancy_pct: float | None = None
    quality_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ConfidenceReport:
    level: Confidence
    score: float
    reasons: list[str]


@dataclass(frozen=True)
class AttentionResult:
    symbol: str
    name: str
    attention_score: int
    severity: Severity
    signals: list[Signal]
    explanation: str
    headline: str
    changed_since_last_visit: bool
    confidence: ConfidenceReport
    # measurements the UI renders directly
    price: float
    change_since_visit_pct: float
    change_today_pct: float
    change_week_pct: float | None
    sector_change_pct: float | None
    market_change_pct: float | None
    relative_edge_pct: float | None
    volume_ratio: float | None
    sigma_multiple: float | None
    baseline: Baseline
    freshness: str
    data_age_seconds: float
    as_of: datetime
    events: list[EventInput]
    #: Stable identity for the change this represents; used to avoid re-alerting.
    fingerprint: str
