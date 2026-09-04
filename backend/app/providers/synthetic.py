"""Deterministic synthetic market.

Design rules that make this useful for a demo *and* defensible engineering:

1.  Reproducible. Prices are a pure function of (scenario, symbol, wall-clock).
    Refreshing the page does not reroll the dice; the tape moves because time
    moved. Restart the process and you get the identical tape back.
2.  Continuous. The intraday path starts exactly at yesterday's close from the
    daily history, so "today %", "this week %" and the sparkline all agree.
3.  Internally consistent. Sector and market benchmarks are aggregates of the
    same instruments, so relative-performance claims are arithmetic.
4.  Time-adjusted volume. We compare volume traded so far against the volume
    you would *expect* by this point in the session, not against a full day.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

from . import universe
from .universe import Instrument

MINUTES_PER_SESSION = 1440  # the demo tape trades continuously
HISTORY_DAYS = 90
TRADING_DAYS_PER_YEAR = 252
#: The demo tape carries less intraday noise than the historical series, so a
#: scripted move reads as a signal rather than drowning in the random walk.
#: Ordinary names therefore sit quietly inside their range, which is exactly the
#: state the product exists to communicate.
INTRADAY_NOISE_SCALE = 0.45


# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SymbolOverlay:
    """A scripted deviation layered on top of the random walk.

    The window is expressed in minutes *before the scenario anchor* rather than
    as an absolute time of day, so a scripted move always lands in the recent
    past no matter what hour the demo is run at — while staying deterministic,
    because the anchor is fixed the moment a scenario is selected.
    """

    total_drift: float = 0.0  # fractional move added across the window
    volume_multiplier: float = 1.0
    window: tuple[int, int] = (110, 12)  # (starts N min ago, ends M min ago)


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    description: str
    overlays: dict[str, SymbolOverlay]
    market_volume_multiplier: float = 1.0
    market_vol_multiplier: float = 1.0
    # provider behaviour
    primary_lag_s: int = 0
    conflict_symbols: tuple[str, ...] = ()
    conflict_magnitude: float = 0.0
    #: (symbol, headline, kind, minutes_before_anchor)
    events: tuple[tuple[str, str, str, int], ...] = ()


SCENARIOS: dict[str, Scenario] = {
    "NORMAL_MARKET": Scenario(
        key="NORMAL_MARKET",
        label="Normal market",
        description="No scripted shocks. Most names stay inside their usual range.",
        overlays={},
    ),
    "NVDA_BREAKOUT": Scenario(
        key="NVDA_BREAKOUT",
        label="NVDA breakout",
        description="NVDA runs on heavy volume and pulls part of the semi complex with it.",
        overlays={
            "NVDA": SymbolOverlay(total_drift=0.042, volume_multiplier=2.4),
            "AMD": SymbolOverlay(total_drift=0.018, volume_multiplier=1.5),
            "TSM": SymbolOverlay(total_drift=0.009, volume_multiplier=1.2),
            "AVGO": SymbolOverlay(total_drift=0.006, volume_multiplier=1.1),
        },
        events=(
            ("NVDA", "Datacenter revenue guidance raised for the coming quarter", "guidance", 96),
            ("NVDA", "Two brokers lift price targets after supply commentary", "analyst", 54),
        ),
    ),
    "TSLA_DROP": Scenario(
        key="TSLA_DROP",
        label="TSLA drawdown",
        description="TSLA sells off on above-average volume while the rest of the tape is quiet.",
        overlays={
            "TSLA": SymbolOverlay(total_drift=-0.0312, volume_multiplier=2.1),
            "RIVN": SymbolOverlay(total_drift=-0.014, volume_multiplier=1.4),
        },
        events=(("TSLA", "Quarterly delivery estimate cut by a sell-side analyst", "analyst", 88),),
    ),
    "HIGH_VOLUME_EVENT": Scenario(
        key="HIGH_VOLUME_EVENT",
        label="Macro print",
        description="A macro release lifts volume and volatility across the whole tape.",
        overlays={
            "JPM": SymbolOverlay(total_drift=0.021, volume_multiplier=2.2),
            "GS": SymbolOverlay(total_drift=0.026, volume_multiplier=2.0),
            "XOM": SymbolOverlay(total_drift=-0.017, volume_multiplier=1.9),
        },
        market_volume_multiplier=1.8,
        market_vol_multiplier=1.6,
        events=(
            ("JPM", "Inflation print lands below consensus", "macro", 104),
            ("GS", "Rate-cut odds repriced across the curve", "macro", 101),
        ),
    ),
    "STALE_PROVIDER": Scenario(
        key="STALE_PROVIDER",
        label="Stale primary feed",
        description="The primary feed stops updating. Confidence should drop and the UI should say so.",
        overlays={"NVDA": SymbolOverlay(total_drift=0.022, volume_multiplier=1.6)},
        primary_lag_s=1500,
    ),
    "CONFLICTING_PROVIDER": Scenario(
        key="CONFLICTING_PROVIDER",
        label="Providers disagree",
        description="The two feeds quote different prices. The reconciler must pick one and record it.",
        overlays={"AAPL": SymbolOverlay(total_drift=0.021, volume_multiplier=1.3)},
        conflict_symbols=("AAPL", "MSFT", "TSLA"),
        conflict_magnitude=0.012,
    ),
}

DEFAULT_SCENARIO = "NVDA_BREAKOUT"


def get_scenario(key: str | None) -> Scenario:
    return SCENARIOS.get((key or "").upper(), SCENARIOS[DEFAULT_SCENARIO])


# ---------------------------------------------------------------------------
# deterministic randomness
# ---------------------------------------------------------------------------


def _seed(*parts: object) -> int:
    raw = "|".join(str(p) for p in parts).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")


def _session_day(now: datetime) -> date:
    return now.astimezone(UTC).date()


def _session_fraction(now: datetime) -> float:
    n = now.astimezone(UTC)
    minutes = n.hour * 60 + n.minute + n.second / 60.0
    return min(1.0, max(0.0, minutes / MINUTES_PER_SESSION))


def current_minute(now: datetime) -> int:
    """Minute index into the demo session, used as the scenario anchor."""
    return int(_session_fraction(now) * MINUTES_PER_SESSION)


def _overlay_window(overlay: "SymbolOverlay | None", anchor_minute: int) -> tuple[int, int]:
    """(first minute of the scripted move, length in minutes)."""
    if overlay is None:
        return 0, MINUTES_PER_SESSION
    start_before, end_before = overlay.window
    start = max(0, anchor_minute - start_before)
    end = max(start + 1, anchor_minute - end_before)
    return start, max(1, end - start)


def _volume_profile_cdf(fraction: float) -> float:
    """Share of a session's volume expected to have traded by `fraction`.

    U-shaped: heavy at the open and into the close. Integrates to 1.0 and is
    floored so early-session ratios do not explode.
    """
    f = min(1.0, max(0.0, fraction))
    # CDF of a normalised U-shape density  d(x) = 1 + a*(2x-1)^2  scaled to 1.
    a = 1.6
    norm = 1.0 + a / 3.0
    cdf = (f + a * ((2 * f - 1) ** 3 + 1) / 6.0) / norm
    return max(0.02, min(1.0, cdf))


# ---------------------------------------------------------------------------
# daily history
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DailyBar:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@lru_cache(maxsize=512)
def daily_history(symbol: str, as_of: date, days: int = HISTORY_DAYS) -> tuple[DailyBar, ...]:
    """`days` daily bars ending on the session before `as_of`.

    The series is rescaled so the final close equals the instrument's reference
    price, which makes it the anchor for the intraday path.
    """
    inst = universe.get(symbol)
    if inst is None:
        return ()

    rng = random.Random(_seed("history", symbol, as_of.isoformat(), days))
    daily_sigma = inst.annual_vol / math.sqrt(TRADING_DAYS_PER_YEAR)

    closes: list[float] = [1.0]
    for _ in range(days):
        shock = rng.gauss(0.0, daily_sigma)
        drift = -0.5 * daily_sigma**2
        closes.append(closes[-1] * math.exp(drift + shock))

    scale = inst.base_price / closes[-1]
    bars: list[DailyBar] = []
    for i in range(1, len(closes)):
        prev_close = closes[i - 1] * scale
        close = closes[i] * scale
        day = as_of - timedelta(days=days - i)
        intraday = abs(rng.gauss(0.0, daily_sigma * 0.6))
        high = max(prev_close, close) * (1 + intraday)
        low = min(prev_close, close) * (1 - intraday)
        vol = int(inst.avg_daily_volume * math.exp(rng.gauss(0.0, 0.28)))
        bars.append(DailyBar(day, round(prev_close, 4), round(high, 4), round(low, 4), round(close, 4), vol))
    return tuple(bars)


@lru_cache(maxsize=512)
def history_stats(symbol: str, as_of: date) -> dict[str, float]:
    """Statistics the attention engine needs to judge "unusual for this stock"."""
    bars = daily_history(symbol, as_of)
    if len(bars) < 25:
        return {}

    returns = [
        (bars[i].close - bars[i - 1].close) / bars[i - 1].close for i in range(1, len(bars))
    ]
    mean = sum(returns) / len(returns)
    var = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
    sigma = math.sqrt(var)

    recent_vols = [b.volume for b in bars[-20:]]
    return {
        "daily_sigma": sigma,
        "mean_return": mean,
        "avg_volume_20d": sum(recent_vols) / len(recent_vols),
        "prev_close": bars[-1].close,
        "week_ago_close": bars[-6].close if len(bars) >= 6 else bars[0].close,
        "month_ago_close": bars[-22].close if len(bars) >= 22 else bars[0].close,
        "range_high_90d": max(b.high for b in bars),
        "range_low_90d": min(b.low for b in bars),
        "sample_size": float(len(bars)),
    }


# ---------------------------------------------------------------------------
# intraday path
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4096)
def _intraday_path(
    scenario_key: str, symbol: str, day: date, anchor_minute: int
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """(prices, cumulative_volume) sampled once per minute for the session."""
    inst = universe.get(symbol)
    scenario = get_scenario(scenario_key)
    if inst is None:
        return ((), ())

    stats = history_stats(symbol, day)
    open_price = stats.get("prev_close", inst.base_price)

    rng = random.Random(_seed("intraday", scenario_key, symbol, day.isoformat()))
    daily_sigma = (inst.annual_vol / math.sqrt(TRADING_DAYS_PER_YEAR)) * scenario.market_vol_multiplier
    step_sigma = daily_sigma * INTRADAY_NOISE_SCALE / math.sqrt(MINUTES_PER_SESSION)

    overlay = scenario.overlays.get(symbol)
    win_start_i, win_len = _overlay_window(overlay, anchor_minute)
    per_step_drift = (overlay.total_drift / win_len) if overlay else 0.0

    prices: list[float] = [open_price]
    volumes: list[float] = [0.0]
    day_volume = inst.avg_daily_volume * math.exp(rng.gauss(0.0, 0.18))
    day_volume *= scenario.market_volume_multiplier
    if overlay:
        day_volume *= overlay.volume_multiplier

    for i in range(1, MINUTES_PER_SESSION + 1):
        shock = rng.gauss(0.0, step_sigma)
        drift = -0.5 * step_sigma**2
        if overlay and win_start_i <= i < win_start_i + win_len:
            drift += per_step_drift
        prices.append(prices[-1] * math.exp(drift + shock))

        expected = _volume_profile_cdf(i / MINUTES_PER_SESSION) * day_volume
        # Volume never decreases, and clusters around the scripted window.
        boost = 1.0
        if overlay and win_start_i <= i < win_start_i + win_len:
            boost = 1.0 + (overlay.volume_multiplier - 1.0) * 0.4
        volumes.append(max(volumes[-1], expected * boost))

    return tuple(prices), tuple(volumes)


@dataclass(frozen=True)
class SyntheticTick:
    symbol: str
    price: float
    open_price: float
    prev_close: float
    day_high: float
    day_low: float
    volume: int
    as_of: datetime


def tick(
    symbol: str, now: datetime, scenario_key: str, anchor_minute: int
) -> SyntheticTick | None:
    inst = universe.get(symbol)
    if inst is None:
        return None

    day = _session_day(now)
    prices, volumes = _intraday_path(scenario_key, inst.symbol, day, anchor_minute)
    if not prices:
        return None

    fraction = _session_fraction(now)
    idx = min(len(prices) - 1, int(fraction * MINUTES_PER_SESSION))
    window = prices[: idx + 1]

    return SyntheticTick(
        symbol=inst.symbol,
        price=round(prices[idx], 4),
        open_price=round(prices[0], 4),
        prev_close=round(history_stats(inst.symbol, day).get("prev_close", inst.base_price), 4),
        day_high=round(max(window), 4),
        day_low=round(min(window), 4),
        volume=int(volumes[idx]),
        as_of=now,
    )


def expected_volume_fraction(now: datetime) -> float:
    return _volume_profile_cdf(_session_fraction(now))


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SyntheticEvent:
    id: str
    symbol: str
    headline: str
    kind: str
    occurred_at: datetime


def events_for(
    symbols: set[str], now: datetime, scenario_key: str, anchor_minute: int
) -> list[SyntheticEvent]:
    scenario = get_scenario(scenario_key)
    day = _session_day(now)
    current_minute = int(_session_fraction(now) * MINUTES_PER_SESSION)
    midnight = datetime.combine(day, datetime.min.time(), tzinfo=UTC)

    out: list[SyntheticEvent] = []
    for symbol, headline, kind, minutes_before in scenario.events:
        at_minute = max(0, anchor_minute - minutes_before)
        if symbol not in symbols or at_minute > current_minute:
            continue
        occurred = midnight + timedelta(minutes=at_minute)
        # Stable id so repeated polling never duplicates an event.
        eid = hashlib.sha1(
            f"{scenario.key}|{symbol}|{headline}|{day}|{anchor_minute}".encode()
        ).hexdigest()[:16]
        out.append(SyntheticEvent(eid, symbol, headline, kind, occurred))
    out.sort(key=lambda e: e.occurred_at, reverse=True)
    return out


def reset_caches() -> None:
    """Used by tests and by the scenario switch."""
    _intraday_path.cache_clear()
    daily_history.cache_clear()
    history_stats.cache_clear()
