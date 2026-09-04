from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.providers import synthetic
from app.providers.base import (
    HistoryPoint,
    MarketDataProvider,
    ProviderTimeout,
    ProviderUnavailable,
    RawQuote,
)
from app.providers.mock import MarketState, MirrorProvider, SyntheticProvider
from app.providers.registry import ProviderRegistry


def quote(symbol: str, price: float, source: str, age_s: float = 0.0) -> RawQuote:
    return RawQuote(
        symbol=symbol,
        price=price,
        prev_close=100.0,
        open_price=100.0,
        day_high=price,
        day_low=99.0,
        volume=1_000,
        as_of=datetime.now(UTC) - timedelta(seconds=age_s),
        source=source,
    )


class FakeProvider(MarketDataProvider):
    def __init__(self, name: str, priority: int, prices: dict[str, float], age_s: float = 0.0, fail: Exception | None = None):
        self.name = name
        self.priority = priority
        self.prices = prices
        self.age_s = age_s
        self.fail = fail

    def get_quotes(self, symbols: list[str]) -> dict[str, RawQuote]:
        if self.fail:
            raise self.fail
        return {s: quote(s, self.prices[s], self.name, self.age_s) for s in symbols if s in self.prices}

    def get_history(self, symbol: str, days: int) -> list[HistoryPoint]:
        return []


def test_agreeing_providers_produce_a_corroborated_quote():
    registry = ProviderRegistry(
        [FakeProvider("a", 10, {"X": 100.0}), FakeProvider("b", 20, {"X": 100.2})]
    )
    batch = registry.get_quotes(["X"])
    assert batch.quotes["X"].price == 100.0  # priority wins
    assert batch.quotes["X"].quality.sources_agreeing == 2
    assert batch.discrepancies == []


def test_disagreement_is_recorded_and_the_trusted_source_is_kept():
    registry = ProviderRegistry(
        [FakeProvider("primary", 10, {"X": 100.0}), FakeProvider("secondary", 20, {"X": 103.0})]
    )
    batch = registry.get_quotes(["X"])
    q = batch.quotes["X"]
    assert q.price == 100.0, "must not silently overwrite with the lower-priority feed"
    assert q.quality.has_conflict
    assert q.quality.discrepancy_pct == pytest.approx(3.0, abs=0.01)
    assert len(batch.discrepancies) == 1
    assert batch.discrepancies[0].primary_source == "primary"
    assert any("disagree" in note for note in q.quality.notes)


def test_one_failing_provider_does_not_break_the_batch():
    registry = ProviderRegistry(
        [
            FakeProvider("primary", 10, {}, fail=ProviderUnavailable("down")),
            FakeProvider("secondary", 20, {"X": 99.5}),
        ]
    )
    batch = registry.get_quotes(["X"])
    assert batch.quotes["X"].price == 99.5
    assert batch.degraded is True
    assert any(not h.ok for h in batch.provider_health)


def test_total_outage_falls_back_to_the_last_known_good_quote():
    good = FakeProvider("primary", 10, {"X": 100.0})
    registry = ProviderRegistry([good])
    registry.get_quotes(["X"])  # warm the safety net

    good.fail = ProviderTimeout("timeout")
    batch = registry.get_quotes(["X"])
    q = batch.quotes["X"]
    assert q.price == 100.0
    assert "cached" in q.quality.selected_source
    assert any("last verified snapshot" in note for note in q.quality.notes)


def test_unknown_symbol_is_reported_not_invented():
    registry = ProviderRegistry([FakeProvider("primary", 10, {"X": 100.0})])
    batch = registry.get_quotes(["X", "NOPE"])
    assert "NOPE" not in batch.quotes
    assert batch.missing == ["NOPE"]


def test_freshness_states_follow_the_age_of_the_quote():
    fresh = ProviderRegistry([FakeProvider("a", 10, {"X": 1.0}, age_s=5)]).get_quotes(["X"])
    delayed = ProviderRegistry([FakeProvider("a", 10, {"X": 1.0}, age_s=600)]).get_quotes(["X"])
    stale = ProviderRegistry([FakeProvider("a", 10, {"X": 1.0}, age_s=2800)]).get_quotes(["X"])
    assert fresh.quotes["X"].quality.freshness == "fresh"
    assert delayed.quotes["X"].quality.freshness == "delayed"
    assert stale.quotes["X"].quality.freshness == "stale"


def test_empty_request_is_handled():
    assert ProviderRegistry([FakeProvider("a", 10, {})]).get_quotes([]).quotes == {}


# --- the synthetic tape --------------------------------------------------------


def test_the_tape_is_reproducible():
    state = MarketState()
    provider = SyntheticProvider(state)
    first = provider.get_quotes(["NVDA"])["NVDA"].price
    synthetic.reset_caches()
    second = provider.get_quotes(["NVDA"])["NVDA"].price
    assert first == pytest.approx(second, rel=1e-9)


def test_scenarios_change_the_tape_and_the_anchor():
    state = MarketState()
    provider = SyntheticProvider(state)
    normal = provider.get_quotes(["NVDA"])["NVDA"].price
    state.select_scenario("TSLA_DROP")
    dropped = provider.get_quotes(["TSLA"])["TSLA"].price
    tsla_prev = provider.get_quotes(["TSLA"])["TSLA"].prev_close
    assert normal > 0
    assert dropped < tsla_prev, "the scripted drawdown should be visible immediately"


def test_stale_scenario_produces_old_timestamps():
    state = MarketState()
    state.select_scenario("STALE_PROVIDER")
    q = SyntheticProvider(state).get_quotes(["NVDA"])["NVDA"]
    assert (datetime.now(UTC) - q.as_of).total_seconds() > 900


def test_conflicting_scenario_makes_the_feeds_disagree():
    state = MarketState()
    state.select_scenario("CONFLICTING_PROVIDER")
    registry = ProviderRegistry([SyntheticProvider(state), MirrorProvider(state)])
    batch = registry.get_quotes(["AAPL", "NVDA"])
    assert batch.quotes["AAPL"].quality.has_conflict
    assert not batch.quotes["NVDA"].quality.has_conflict


def test_history_ends_at_the_reference_price():
    bars = synthetic.daily_history("NVDA", datetime.now(UTC).date())
    assert len(bars) == synthetic.HISTORY_DAYS
    assert bars[-1].close == pytest.approx(171.42, rel=1e-6)


def test_volume_profile_is_monotonic():
    values = [synthetic._volume_profile_cdf(i / 20) for i in range(21)]
    assert values == sorted(values)
    assert values[-1] == pytest.approx(1.0, abs=1e-6)
