from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.attention.engine import AttentionEngine
from app.domain.attention.types import (
    AttentionInput,
    Baseline,
    Confidence,
    EventInput,
    MarketContext,
    Severity,
    SignalType,
)
from app.domain.attention.weights import AttentionWeights

NOW = datetime(2026, 3, 2, 15, 30, tzinfo=UTC)


def make_input(**overrides) -> AttentionInput:
    base = dict(
        symbol="NVDA",
        name="NVIDIA Corporation",
        price=178.63,
        prev_close=172.05,
        open_price=172.40,
        volume=190_000_000,
        as_of=NOW,
        expected_volume_fraction=0.55,
        avg_volume_20d=214_000_000,
        daily_sigma=0.033,
        history_sample=90,
        week_ago_close=167.40,
        baseline=Baseline(price=171.42, volume=90_000_000, observed_at=NOW - timedelta(hours=3, minutes=18), source="last_visit"),
        context=MarketContext(
            sector_code="SEMI",
            sector_label="Semiconductors",
            sector_change_pct=1.10,
            market_change_pct=0.42,
            beta=1.72,
        ),
        events=[],
        freshness="fresh",
        data_age_seconds=8.0,
    )
    base.update(overrides)
    return AttentionInput(**base)


def test_scoring_is_deterministic():
    engine = AttentionEngine()
    data = make_input()
    first = engine.score(data)
    second = engine.score(data)
    assert first.attention_score == second.attention_score
    assert first.fingerprint == second.fingerprint
    assert [s.contribution for s in first.signals] == [s.contribution for s in second.signals]


def test_large_move_on_heavy_volume_is_high_severity():
    result = AttentionEngine().score(make_input())
    assert result.attention_score >= 70
    assert result.severity is Severity.HIGH
    assert result.changed_since_last_visit is True


def test_quiet_stock_is_not_promoted():
    result = AttentionEngine().score(
        make_input(
            price=171.60,
            prev_close=171.30,
            open_price=171.35,
            volume=90_000_000,
            context=MarketContext("SEMI", "Semiconductors", 0.10, 0.08, 1.72),
        )
    )
    assert result.severity is Severity.NONE
    assert result.changed_since_last_visit is False
    assert "normal range" in result.explanation or "in line" in result.explanation


def test_score_is_the_sum_of_its_signals():
    """The explanation can never disagree with the number."""
    result = AttentionEngine().score(make_input())
    total = sum(s.contribution for s in result.signals)
    assert result.attention_score == round(min(100.0, total))


def test_move_is_normalised_by_the_stock_s_own_volatility():
    """Two per cent in a sleepy name outranks two per cent in a volatile one."""
    engine = AttentionEngine()
    calm = engine.score(make_input(symbol="COST", daily_sigma=0.011, price=175.0, prev_close=171.42))
    wild = engine.score(make_input(symbol="RIVN", daily_sigma=0.070, price=175.0, prev_close=171.42))
    calm_price = next(s for s in calm.signals if s.type is SignalType.PRICE_MOVE)
    wild_price = next(s for s in wild.signals if s.type is SignalType.PRICE_MOVE)
    assert calm_price.contribution > wild_price.contribution


def test_volume_ratio_is_time_adjusted():
    """Early in the session, a small absolute volume can still be a big anomaly."""
    engine = AttentionEngine()
    early = engine.score(make_input(volume=60_000_000, expected_volume_fraction=0.10))
    assert early.volume_ratio == pytest.approx(60_000_000 / (214_000_000 * 0.10), rel=1e-3)
    assert early.volume_ratio > 2.0


def test_stale_data_lowers_confidence_not_the_score():
    engine = AttentionEngine()
    fresh = engine.score(make_input())
    stale = engine.score(make_input(freshness="stale", data_age_seconds=2820))
    assert stale.attention_score == fresh.attention_score
    assert stale.confidence.level is not Confidence.HIGH
    assert any("stale" in reason for reason in stale.confidence.reasons)


def test_provider_conflict_is_reflected_in_confidence():
    result = AttentionEngine().score(make_input(has_conflict=True, discrepancy_pct=1.2))
    assert any("disagree" in reason for reason in result.confidence.reasons)
    assert result.confidence.score < 1.0


def test_missing_history_degrades_gracefully():
    result = AttentionEngine().score(
        make_input(daily_sigma=None, avg_volume_20d=None, history_sample=0)
    )
    assert result.attention_score >= 0
    assert result.volume_ratio is None
    unusual = next(s for s in result.signals if s.type is SignalType.HISTORICAL_UNUSUALNESS)
    assert unusual.contribution == 0.0
    assert result.confidence.level is Confidence.LOW


def test_missing_sector_benchmark_does_not_crash():
    result = AttentionEngine().score(
        make_input(context=MarketContext("SEMI", "Semiconductors", None, None, 1.0))
    )
    assert result.relative_edge_pct is None
    assert any("No sector benchmark" in reason for reason in result.confidence.reasons)


def test_events_after_the_baseline_count_and_earlier_ones_do_not():
    engine = AttentionEngine()
    old = EventInput("e1", "Old news", "analyst", NOW - timedelta(hours=9))
    new = EventInput("e2", "Guidance raised", "guidance", NOW - timedelta(minutes=40))
    ignored = engine.score(make_input(events=[old]))
    counted = engine.score(make_input(events=[new]))
    assert ignored.events == []
    assert counted.events and counted.events[0].id == "e2"
    assert next(s for s in counted.signals if s.type is SignalType.EVENT).contribution > 0


def test_weights_are_configurable():
    default = AttentionEngine().score(make_input())
    heavy = AttentionEngine(AttentionWeights(price_move=60.0)).score(make_input())
    assert heavy.attention_score > default.attention_score


def test_thresholds_are_configurable():
    quiet_profile = AttentionWeights(high_threshold=95.0, medium_threshold=90.0)
    result = AttentionEngine(quiet_profile).score(make_input())
    assert result.severity is not Severity.HIGH


def test_fingerprint_is_stable_for_small_drift_and_changes_on_escalation():
    engine = AttentionEngine()
    a = engine.score(make_input(price=178.63))
    b = engine.score(make_input(price=178.90))  # same change, marginally further
    c = engine.score(make_input(price=205.00))  # a genuinely bigger event
    assert a.fingerprint == b.fingerprint
    assert a.fingerprint != c.fingerprint


def test_short_window_does_not_manufacture_sigma_events():
    """A 40-second gap must not make every tick look like a five-sigma move."""
    result = AttentionEngine().score(
        make_input(
            baseline=Baseline(171.42, None, NOW - timedelta(seconds=40), "last_visit"),
            price=172.20,
        )
    )
    assert result.sigma_multiple is not None
    assert result.sigma_multiple < 3.0


def test_baseline_fallback_is_declared():
    result = AttentionEngine().score(
        make_input(baseline=Baseline(172.40, None, NOW - timedelta(hours=6), "session_open"))
    )
    assert any("previous visit" in reason for reason in result.confidence.reasons)
