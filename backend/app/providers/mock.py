"""Mock providers.

Two of them, deliberately. One provider can never demonstrate reconciliation,
and reconciliation is where most real market-data bugs live.

`SyntheticProvider` reads the deterministic tape. `MirrorProvider` reads the
same tape but applies a small independent measurement error, and — under the
CONFLICTING_PROVIDER scenario — a large one on selected symbols.
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime, timedelta

from . import synthetic, universe
from .base import (
    HistoryPoint,
    MarketDataProvider,
    ProviderHealth,
    ProviderTimeout,
    ProviderUnavailable,
    RawEvent,
    RawQuote,
)


class MarketState:
    """Runtime demo controls. Small, explicit, and observable.

    `anchor_minute` pins where a scenario's scripted move sits in the session.
    It is set when a scenario is selected and never drifts afterwards, which is
    what keeps the tape reproducible while still guaranteeing the scripted move
    is visible immediately rather than at some fixed hour of the day.
    """

    def __init__(self) -> None:
        self.scenario: str = synthetic.DEFAULT_SCENARIO
        self.primary_outage: bool = False
        self.secondary_outage: bool = False
        self.anchor_minute: int = synthetic.current_minute(datetime.now(UTC))

    def select_scenario(self, key: str, now: datetime | None = None) -> None:
        self.scenario = key
        self.anchor_minute = synthetic.current_minute(now or datetime.now(UTC))

    def snapshot(self) -> dict[str, object]:
        return {
            "scenario": self.scenario,
            "primary_outage": self.primary_outage,
            "secondary_outage": self.secondary_outage,
            "anchor_minute": self.anchor_minute,
        }


market_state = MarketState()


def _now() -> datetime:
    return datetime.now(UTC)


class SyntheticProvider(MarketDataProvider):
    """Primary feed."""

    name = "synthetic-primary"
    priority = 10

    def __init__(self, state: MarketState) -> None:
        self.state = state

    def _guard(self) -> None:
        if self.state.primary_outage:
            raise ProviderUnavailable("primary feed is not responding")

    def get_quotes(self, symbols: list[str]) -> dict[str, RawQuote]:
        self._guard()
        scenario = synthetic.get_scenario(self.state.scenario)
        # A lagging feed still answers — it just answers with old data. This is
        # the failure mode people actually get wrong.
        as_of = _now() - timedelta(seconds=scenario.primary_lag_s)

        out: dict[str, RawQuote] = {}
        for symbol in symbols:
            t = synthetic.tick(symbol, as_of, self.state.scenario, self.state.anchor_minute)
            if t is None:
                continue  # unknown symbol: omit rather than invent
            out[symbol] = RawQuote(
                symbol=t.symbol,
                price=t.price,
                prev_close=t.prev_close,
                open_price=t.open_price,
                day_high=t.day_high,
                day_low=t.day_low,
                volume=t.volume,
                as_of=t.as_of,
                source=self.name,
            )
        return out

    def get_history(self, symbol: str, days: int) -> list[HistoryPoint]:
        self._guard()
        bars = synthetic.daily_history(symbol.upper(), _now().date())
        return [
            HistoryPoint(day=b.day.isoformat(), close=b.close, volume=b.volume)
            for b in bars[-days:]
        ]

    def get_events(self, symbols: list[str]) -> list[RawEvent]:
        self._guard()
        found = synthetic.events_for(
            set(symbols), _now(), self.state.scenario, self.state.anchor_minute
        )
        return [
            RawEvent(e.id, e.symbol, e.headline, e.kind, e.occurred_at, self.name) for e in found
        ]

    def health(self) -> ProviderHealth:
        start = time.perf_counter()
        ok = not self.state.primary_outage
        return ProviderHealth(
            self.name,
            self.priority,
            ok,
            (time.perf_counter() - start) * 1000,
            "" if ok else "simulated outage",
        )


class MirrorProvider(MarketDataProvider):
    """Secondary feed: same tape, independent measurement error."""

    name = "synthetic-secondary"
    priority = 20

    def __init__(self, state: MarketState) -> None:
        self.state = state

    def _guard(self) -> None:
        if self.state.secondary_outage:
            raise ProviderTimeout("secondary feed timed out")

    def get_quotes(self, symbols: list[str]) -> dict[str, RawQuote]:
        self._guard()
        scenario = synthetic.get_scenario(self.state.scenario)
        now = _now()
        out: dict[str, RawQuote] = {}
        for symbol in symbols:
            t = synthetic.tick(symbol, now, self.state.scenario, self.state.anchor_minute)
            if t is None:
                continue
            # Deterministic sub-basis-point jitter: two real feeds never agree
            # to the last decimal, and the reconciler must tolerate that.
            wobble = math.sin(hash((symbol, now.minute)) % 1000) * 0.0004
            if symbol in scenario.conflict_symbols:
                wobble += scenario.conflict_magnitude
            price = round(t.price * (1 + wobble), 4)
            out[symbol] = RawQuote(
                symbol=t.symbol,
                price=price,
                prev_close=t.prev_close,
                open_price=t.open_price,
                day_high=max(t.day_high, price),
                day_low=min(t.day_low, price),
                volume=int(t.volume * 0.985),
                as_of=now,
                source=self.name,
            )
        return out

    def get_history(self, symbol: str, days: int) -> list[HistoryPoint]:
        self._guard()
        bars = synthetic.daily_history(symbol.upper(), _now().date())
        return [
            HistoryPoint(day=b.day.isoformat(), close=b.close, volume=b.volume)
            for b in bars[-days:]
        ]

    def health(self) -> ProviderHealth:
        ok = not self.state.secondary_outage
        return ProviderHealth(
            self.name, self.priority, ok, 0.0, "" if ok else "simulated timeout"
        )


def known_symbols() -> tuple[str, ...]:
    return universe.ALL_SYMBOLS
