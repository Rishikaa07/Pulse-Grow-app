"""Typed API contracts.

Response models are camelCase on the wire (the frontend is TypeScript) and
snake_case in Python, handled by an alias generator rather than by hand.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.title() for part in tail)


class Schema(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, from_attributes=True)


# --- auth ---------------------------------------------------------------------


class RegisterRequest(Schema):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(Schema):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(Schema):
    id: int
    email: str
    display_name: str
    is_demo: bool
    attention_profile: dict[str, float] = Field(default_factory=dict)


# --- watchlists ---------------------------------------------------------------


class SymbolField(Schema):
    symbol: str = Field(min_length=1, max_length=12)

    @field_validator("symbol")
    @classmethod
    def normalise(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned.isalnum():
            raise ValueError("Symbols may only contain letters and digits.")
        return cleaned


class WatchlistCreate(Schema):
    name: str = Field(min_length=1, max_length=120)
    symbols: list[str] = Field(default_factory=list, max_length=60)


class WatchlistUpdate(Schema):
    name: str = Field(min_length=1, max_length=120)


class ReorderRequest(Schema):
    symbols: list[str] = Field(max_length=60)


class WatchlistItemOut(Schema):
    symbol: str
    name: str
    sector: str
    position: int


class WatchlistOut(Schema):
    id: int
    name: str
    position: int
    item_count: int
    items: list[WatchlistItemOut]


# --- market -------------------------------------------------------------------


class SignalOut(Schema):
    type: str
    value: float
    display: str
    weight: float
    contribution: float
    detail: str


class ConfidenceOut(Schema):
    level: Literal["high", "medium", "low"]
    score: float
    reasons: list[str]


class BaselineOut(Schema):
    price: float
    observed_at: datetime
    source: str


class EventOut(Schema):
    id: str
    headline: str
    kind: str
    occurred_at: datetime


class ChangesOut(Schema):
    since_visit_pct: float
    today_pct: float
    week_pct: float | None


class BenchmarksOut(Schema):
    sector_code: str
    sector_label: str
    sector_change_pct: float | None
    market_change_pct: float | None
    relative_edge_pct: float | None


class FreshnessOut(Schema):
    state: Literal["fresh", "delayed", "stale", "unavailable"]
    age_seconds: float
    source: str
    as_of: datetime
    notes: list[str] = Field(default_factory=list)


class AttentionItemOut(Schema):
    symbol: str
    name: str
    attention_score: int
    severity: Literal["high", "medium", "low", "none"]
    headline: str
    explanation: str
    price: float
    changes: ChangesOut
    benchmarks: BenchmarksOut
    baseline: BaselineOut
    signals: list[SignalOut]
    confidence: ConfidenceOut
    freshness: FreshnessOut
    volume_ratio: float | None
    sigma_multiple: float | None
    changed_since_last_visit: bool
    events: list[EventOut]
    status: Literal["new", "reviewed", "dismissed"]
    change_event_id: int | None
    fingerprint: str


class VisitOut(Schema):
    started_at: datetime
    is_new_visit: bool
    last_visit_at: datetime | None
    away_seconds: float | None
    baseline_source: str


class SummaryOut(Schema):
    tracked: int
    meaningful_changes: int
    unusual_moves: int
    events: int
    quiet: int
    new_in_inbox: int


class IndexOut(Schema):
    key: str
    label: str
    change_today_pct: float


class ProviderHealthOut(Schema):
    name: str
    priority: int
    ok: bool
    detail: str


class DataQualityOut(Schema):
    freshness: Literal["fresh", "delayed", "stale", "unavailable"]
    degraded: bool
    providers: list[ProviderHealthOut]
    discrepancies: list[str]
    missing_symbols: list[str]


class OverviewOut(Schema):
    watchlist: WatchlistOut
    visit: VisitOut
    summary: SummaryOut
    items: list[AttentionItemOut]
    indices: list[IndexOut]
    data_quality: DataQualityOut
    scenario: str
    generated_at: datetime


# --- stock detail --------------------------------------------------------------


class HistoryPointOut(Schema):
    day: str
    close: float
    volume: int


class StockDetailOut(Schema):
    symbol: str
    name: str
    exchange: str
    sector: str
    sector_label: str
    price: float
    prev_close: float
    open_price: float
    day_high: float
    day_low: float
    volume: int
    freshness: FreshnessOut
    stats: dict[str, float]
    history: list[HistoryPointOut]
    events: list[EventOut]


class SearchResultOut(Schema):
    symbol: str
    name: str
    exchange: str
    sector: str
    sector_label: str


# --- inbox ---------------------------------------------------------------------


class ChangeEventOut(Schema):
    id: int
    symbol: str
    attention_score: int
    severity: str
    headline: str
    explanation: str
    signals: list[dict[str, Any]]
    metrics: dict[str, Any]
    confidence: str
    status: str
    detected_at: datetime
    reviewed_at: datetime | None


class ReviewRequest(Schema):
    status: Literal["new", "reviewed", "dismissed"] = "reviewed"


# --- demo controls -------------------------------------------------------------


class ScenarioOut(Schema):
    key: str
    label: str
    description: str


class DemoStateOut(Schema):
    scenario: str
    primary_outage: bool
    secondary_outage: bool
    scenarios: list[ScenarioOut]


class DemoStateRequest(Schema):
    scenario: str | None = None
    primary_outage: bool | None = None
    secondary_outage: bool | None = None


class AttentionProfileRequest(Schema):
    weights: dict[str, float] = Field(default_factory=dict)


class HealthOut(Schema):
    status: str
    database: bool
    cache: str
    providers: list[ProviderHealthOut]
    scenario: str
    version: str
