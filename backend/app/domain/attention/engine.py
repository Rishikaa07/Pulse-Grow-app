"""The Attention Engine.

Given what a stock is doing, what its peers are doing, and what the user last
saw, decide how much of their attention it deserves — and be able to show the
arithmetic.

Two properties matter more than anything else here:

*   **Deterministic.** Same inputs, same score, always. No sampling, no model
    calls, no clock reads inside the scoring path.
*   **Explainable.** Every point in the score is attributable to one signal, and
    every signal carries the measurement that produced it. The English
    explanation is generated *from* the signals, so it can never disagree with
    the number.

Normalisation is the interesting part. A 2% move in Costco and a 2% move in
Rivian are not the same event, so moves are measured in units of that stock's
own recent volatility, scaled to the length of the window being judged.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime

from .types import (
    AttentionInput,
    AttentionResult,
    Baseline,
    Confidence,
    ConfidenceReport,
    EventInput,
    Severity,
    Signal,
    SignalType,
)
from .weights import DEFAULT_WEIGHTS, AttentionWeights

MINUTES_PER_SESSION = 1440
_EPS = 1e-9


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _saturate(z: float, scale: float) -> float:
    """Smooth 0→1 ramp. z=scale ≈ 0.46, z=2·scale ≈ 0.71, z=4·scale ≈ 0.92."""
    if z <= 0:
        return 0.0
    return 1.0 - math.exp(-z / max(scale, _EPS))


def _pct(a: float, b: float) -> float:
    if abs(b) < _EPS:
        return 0.0
    return (a - b) / b * 100.0


def _fmt_pct(value: float) -> str:
    return f"{value:+.2f}%"


class AttentionEngine:
    """Pure scoring service. One instance per request is fine; it holds no state."""

    def __init__(self, weights: AttentionWeights | None = None) -> None:
        self.w = weights or DEFAULT_WEIGHTS

    # -- public API -----------------------------------------------------------

    def score(self, data: AttentionInput) -> AttentionResult:
        w = self.w

        change_since_visit = _pct(data.price, data.baseline.price)
        change_today = _pct(data.price, data.prev_close)
        change_week = (
            _pct(data.price, data.week_ago_close) if data.week_ago_close else None
        )

        window_minutes = self._window_minutes(data.baseline.observed_at, data.as_of)
        sigma_window = self._window_sigma(data.daily_sigma, window_minutes)
        sigma_multiple = (
            abs(change_since_visit) / (sigma_window * 100)
            if sigma_window and sigma_window > _EPS
            else None
        )

        # Relative performance is only meaningful once the stock has actually
        # moved. Without this gate a flat name picks up points merely because
        # its sector drifted, which is exactly the noise this product removes.
        materiality = self._materiality(sigma_multiple, change_since_visit)

        signals: list[Signal] = []
        signals.append(self._price_signal(change_since_visit, sigma_multiple))

        volume_ratio = self._relative_volume(data)
        signals.append(self._volume_signal(volume_ratio))

        sector_excess = (
            change_since_visit - data.context.sector_change_pct
            if data.context.sector_change_pct is not None
            else None
        )
        signals.append(
            self._relative_signal(
                SignalType.SECTOR_OUTPERFORMANCE,
                sector_excess,
                sigma_window,
                w.sector_outperformance,
                data.context.sector_label,
                gate=materiality,
            )
        )

        market_excess = None
        if data.context.market_change_pct is not None:
            expected = data.context.market_change_pct * data.context.beta
            market_excess = change_since_visit - expected
        signals.append(
            self._relative_signal(
                SignalType.MARKET_OUTPERFORMANCE,
                market_excess,
                sigma_window,
                w.market_outperformance,
                "the broad market",
                beta_adjusted=True,
                gate=materiality,
            )
        )

        signals.append(self._unusualness_signal(change_today, data))
        recent_events = [e for e in data.events if e.occurred_at >= data.baseline.observed_at]
        signals.append(self._event_signal(recent_events))
        signals.append(
            self._missed_signal(
                change_since_visit,
                change_today,
                sigma_multiple,
                # "You missed it" is meaningless when the baseline is today's
                # open, because then everything happened while you were away.
                applicable=data.baseline.source == "last_visit",
                gate=materiality,
            )
        )

        raw = sum(s.contribution for s in signals)
        attention = int(round(_clamp(raw, 0.0, 100.0)))
        severity = self._severity(attention)
        confidence = self._confidence(data)

        changed = self._changed_since_visit(
            change_since_visit, sigma_multiple, bool(recent_events)
        )

        material = sorted(
            (s for s in signals if s.is_material),
            key=lambda s: s.contribution,
            reverse=True,
        )
        headline = self._headline(severity, material, change_since_visit, sigma_multiple)
        explanation = self._explain(material, severity, data)

        return AttentionResult(
            symbol=data.symbol,
            name=data.name,
            attention_score=attention,
            severity=severity,
            signals=signals,
            explanation=explanation,
            headline=headline,
            changed_since_last_visit=changed,
            confidence=confidence,
            price=data.price,
            change_since_visit_pct=round(change_since_visit, 4),
            change_today_pct=round(change_today, 4),
            change_week_pct=round(change_week, 4) if change_week is not None else None,
            sector_change_pct=data.context.sector_change_pct,
            market_change_pct=data.context.market_change_pct,
            relative_edge_pct=round(sector_excess, 4) if sector_excess is not None else None,
            volume_ratio=round(volume_ratio, 3) if volume_ratio is not None else None,
            sigma_multiple=round(sigma_multiple, 3) if sigma_multiple is not None else None,
            baseline=data.baseline,
            freshness=data.freshness,
            data_age_seconds=data.data_age_seconds,
            as_of=data.as_of,
            events=recent_events,
            fingerprint=self._fingerprint(data, attention, severity),
        )

    # -- individual signals ---------------------------------------------------

    def _price_signal(self, change_pct: float, sigma_multiple: float | None) -> Signal:
        w = self.w.price_move
        if sigma_multiple is None:
            # No volatility history: fall back to a fixed scale and say so.
            ratio = _saturate(abs(change_pct) / 2.0, 1.0)
            detail = f"Moved {_fmt_pct(change_pct)} since your last check."
            return Signal(
                SignalType.PRICE_MOVE,
                round(change_pct, 4),
                _fmt_pct(change_pct),
                w,
                round(w * ratio, 2),
                detail,
            )

        ratio = _saturate(sigma_multiple, self.w.price_sigma_scale)
        if sigma_multiple >= 2.0:
            detail = (
                f"{_fmt_pct(change_pct)} is {sigma_multiple:.1f}× the move this stock "
                "normally makes over a window this long."
            )
        elif sigma_multiple >= 1.0:
            detail = f"{_fmt_pct(change_pct)} is at the top of its normal range."
        else:
            detail = f"{_fmt_pct(change_pct)} is inside its normal range."
        return Signal(
            SignalType.PRICE_MOVE,
            round(change_pct, 4),
            _fmt_pct(change_pct),
            w,
            round(w * ratio, 2),
            detail,
        )

    def _volume_signal(self, ratio: float | None) -> Signal:
        w = self.w.volume_anomaly
        if ratio is None:
            return Signal(
                SignalType.VOLUME_ANOMALY,
                0.0,
                "unavailable",
                w,
                0.0,
                "No volume baseline available for this symbol.",
            )
        span = max(self.w.volume_ceiling - self.w.volume_floor, _EPS)
        strength = _clamp((ratio - self.w.volume_floor) / span)
        if ratio >= 1.8:
            detail = f"Volume is {ratio:.1f}× what this name usually trades by this point."
        elif ratio >= 1.2:
            detail = f"Volume is running {ratio:.1f}× its usual pace."
        else:
            detail = f"Volume is normal at {ratio:.1f}× its usual pace."
        return Signal(
            SignalType.VOLUME_ANOMALY,
            round(ratio, 3),
            f"{ratio:.1f}× normal",
            w,
            round(w * strength, 2),
            detail,
        )

    def _relative_signal(
        self,
        signal_type: SignalType,
        excess_pct: float | None,
        sigma_window: float | None,
        weight: float,
        benchmark_label: str,
        beta_adjusted: bool = False,
        gate: float = 1.0,
    ) -> Signal:
        if excess_pct is None:
            return Signal(
                signal_type,
                0.0,
                "unavailable",
                weight,
                0.0,
                f"No benchmark available for {benchmark_label}.",
            )

        if sigma_window and sigma_window > _EPS:
            z = abs(excess_pct) / (sigma_window * 100)
        else:
            z = abs(excess_pct) / 1.5
        strength = _clamp(z / self.w.relative_sigma_ceiling) * gate

        direction = "ahead of" if excess_pct >= 0 else "behind"
        qualifier = " once beta is accounted for" if beta_adjusted else ""
        if abs(excess_pct) < 0.25:
            detail = f"Moving with {benchmark_label}{qualifier}."
        else:
            detail = (
                f"{abs(excess_pct):.2f} points {direction} {benchmark_label}{qualifier}."
            )
        return Signal(
            signal_type,
            round(excess_pct, 4),
            _fmt_pct(excess_pct),
            weight,
            round(weight * strength, 2),
            detail,
        )

    def _unusualness_signal(self, change_today: float, data: AttentionInput) -> Signal:
        w = self.w.historical_unusualness
        if not data.daily_sigma or data.history_sample < 25:
            return Signal(
                SignalType.HISTORICAL_UNUSUALNESS,
                0.0,
                "unavailable",
                w,
                0.0,
                "Not enough history to judge whether this is unusual.",
            )

        z = abs(change_today) / (data.daily_sigma * 100 + _EPS)
        # Normal-tail percentile of |return|.
        percentile = math.erf(z / math.sqrt(2))
        floor = self.w.unusual_percentile_floor
        strength = _clamp((percentile - floor) / max(1.0 - floor, _EPS))
        if percentile >= 0.99:
            detail = "Today's move is in the top 1% of this stock's daily history."
        elif percentile >= 0.95:
            detail = "Today's move is bigger than 95% of its recent sessions."
        elif percentile >= floor:
            detail = "Today's move is above its typical daily range."
        else:
            detail = "Today's move is ordinary for this stock."
        return Signal(
            SignalType.HISTORICAL_UNUSUALNESS,
            round(percentile * 100, 2),
            f"{percentile * 100:.0f}th percentile",
            w,
            round(w * strength, 2),
            detail,
        )

    def _event_signal(self, events: list[EventInput]) -> Signal:
        w = self.w.event
        if not events:
            return Signal(
                SignalType.EVENT, 0.0, "none", w, 0.0, "No recorded event in this window."
            )
        kind_weight = {"guidance": 1.0, "macro": 0.9, "analyst": 0.75, "filing": 0.7}
        strength = max(kind_weight.get(e.kind, 0.6) for e in events)
        label = "1 event" if len(events) == 1 else f"{len(events)} events"
        return Signal(
            SignalType.EVENT,
            float(len(events)),
            label,
            w,
            round(w * strength, 2),
            events[0].headline,
        )

    def _missed_signal(
        self,
        since_visit: float,
        today: float,
        sigma_multiple: float | None,
        applicable: bool = True,
        gate: float = 1.0,
    ) -> Signal:
        w = self.w.missed_while_away
        if not applicable:
            return Signal(
                SignalType.MISSED_WHILE_AWAY,
                0.0,
                "—",
                w,
                0.0,
                "No previous visit to compare against.",
            )
        if abs(today) < 0.05 or (sigma_multiple is not None and sigma_multiple < 0.5):
            return Signal(
                SignalType.MISSED_WHILE_AWAY,
                0.0,
                "—",
                w,
                0.0,
                "Little has changed since you were last here.",
            )
        share = _clamp(abs(since_visit) / (abs(today) + _EPS))
        if share < 0.4:
            return Signal(
                SignalType.MISSED_WHILE_AWAY,
                round(share * 100, 1),
                f"{share * 100:.0f}% of today",
                w,
                0.0,
                "Most of today's move happened before your last visit.",
            )
        strength = _clamp((share - 0.4) / 0.6) * gate
        return Signal(
            SignalType.MISSED_WHILE_AWAY,
            round(share * 100, 1),
            f"{share * 100:.0f}% of today",
            w,
            round(w * strength, 2),
            f"{share * 100:.0f}% of today's move happened after you left.",
        )

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _materiality(sigma_multiple: float | None, change_pct: float) -> float:
        """0 to 1: how much of a move there is to have an opinion about.

        Below roughly half a standard deviation nothing is happening, so the
        context signals are damped to zero rather than accumulating points.
        """
        if sigma_multiple is None:
            return _clamp(abs(change_pct) / 1.5)
        return _clamp((sigma_multiple - 0.4) / 0.8)

    @staticmethod
    def _window_minutes(baseline_at: datetime, as_of: datetime) -> float:
        delta = (as_of - baseline_at).total_seconds() / 60.0
        # Floor at 15 minutes: judging a 40-second window against daily sigma
        # makes every tick look like a five-sigma event.
        return max(15.0, min(delta, MINUTES_PER_SESSION * 5))

    @staticmethod
    def _window_sigma(daily_sigma: float | None, window_minutes: float) -> float | None:
        if not daily_sigma:
            return None
        return daily_sigma * math.sqrt(window_minutes / MINUTES_PER_SESSION)

    @staticmethod
    def _relative_volume(data: AttentionInput) -> float | None:
        if not data.avg_volume_20d or data.avg_volume_20d <= 0:
            return None
        expected = data.avg_volume_20d * max(data.expected_volume_fraction, 0.02)
        if expected <= 0:
            return None
        return data.volume / expected

    def _severity(self, score: int) -> Severity:
        if score >= self.w.high_threshold:
            return Severity.HIGH
        if score >= self.w.medium_threshold:
            return Severity.MEDIUM
        if score >= self.w.low_threshold:
            return Severity.LOW
        return Severity.NONE

    def _changed_since_visit(
        self, change_pct: float, sigma_multiple: float | None, has_event: bool
    ) -> bool:
        if has_event:
            return True
        if abs(change_pct) >= self.w.change_abs_floor_pct:
            return True
        if sigma_multiple is not None and sigma_multiple >= self.w.change_sigma_floor:
            return True
        return False

    def _confidence(self, data: AttentionInput) -> ConfidenceReport:
        score = 1.0
        reasons: list[str] = []

        penalty = {"fresh": 0.0, "delayed": 0.12, "stale": 0.35, "unavailable": 0.6}
        drop = penalty.get(data.freshness, 0.3)
        if drop:
            score -= drop
            minutes = int(data.data_age_seconds // 60)
            reasons.append(
                f"Price is {data.freshness}; last update was {minutes} minute"
                f"{'s' if minutes != 1 else ''} ago."
            )

        if data.has_conflict:
            score -= 0.15
            pct = data.discrepancy_pct or 0.0
            reasons.append(f"Feeds disagree by {pct:.2f}% on this symbol.")

        if data.history_sample < 25:
            score -= 0.3
            reasons.append("Limited price history, so 'unusual' is a weaker judgement.")

        if data.context.sector_change_pct is None:
            score -= 0.1
            reasons.append("No sector benchmark available for comparison.")

        if data.avg_volume_20d is None:
            score -= 0.15
            reasons.append("No volume baseline available.")

        if data.baseline.source != "last_visit":
            score -= 0.05
            reasons.append("No previous visit recorded; comparing against today's open.")

        score = _clamp(score)
        level = (
            Confidence.HIGH if score >= 0.8 else Confidence.MEDIUM if score >= 0.6 else Confidence.LOW
        )
        return ConfidenceReport(level, round(score, 3), reasons)

    def _headline(
        self,
        severity: Severity,
        material: list[Signal],
        change_pct: float,
        sigma_multiple: float | None,
    ) -> str:
        if severity is Severity.NONE:
            return "Moving with the market"

        # Only a signal that used a real share of its budget gets to name the
        # row. Otherwise a 0.4% drift ends up headlined "unusually large move".
        dominant = [s for s in material if s.weight > 0 and s.contribution >= 0.45 * s.weight]
        if not dominant:
            return "Worth a look"

        top = dominant[0].type
        direction = "up" if change_pct >= 0 else "down"
        if top is SignalType.PRICE_MOVE:
            # The same threshold the detail text uses, so the two always agree.
            if sigma_multiple is not None and sigma_multiple >= 2.0:
                return f"Unusually large move {direction}"
            return f"Notable move {direction}"
        return {
            SignalType.VOLUME_ANOMALY: "Unusual activity detected",
            SignalType.SECTOR_OUTPERFORMANCE: (
                "Outperforming its sector" if change_pct >= 0 else "Lagging its sector"
            ),
            SignalType.MARKET_OUTPERFORMANCE: (
                "Outperforming the market" if change_pct >= 0 else "Lagging the market"
            ),
            SignalType.HISTORICAL_UNUSUALNESS: "Outside its normal range",
            SignalType.EVENT: "Event detected",
            SignalType.MISSED_WHILE_AWAY: "Moved while you were away",
        }.get(top, "Worth a look")

    def _explain(
        self, material: list[Signal], severity: Severity, data: AttentionInput
    ) -> str:
        if severity is Severity.NONE or not material:
            return (
                f"{data.symbol} stayed inside its normal range and moved broadly in line "
                f"with {data.context.sector_label.lower()}."
            )
        clauses = [s.detail.rstrip(".") for s in material[:3]]
        sentence = clauses[0] + "."
        if len(clauses) > 1:
            sentence += " " + " ".join(c + "." for c in clauses[1:])
        return sentence

    @staticmethod
    def _fingerprint(data: AttentionInput, score: int, severity: Severity) -> str:
        """Identity of *this change*, not of this poll.

        The score is bucketed so that a 71 drifting to a 73 is the same change
        and does not resurface in the inbox, while a genuine escalation does.
        """
        bucket = score // 10
        event_ids = ",".join(sorted(e.id for e in data.events))
        raw = (
            f"{data.symbol}|{data.baseline.observed_at.isoformat()}|{severity}|"
            f"{bucket}|{event_ids}"
        )
        return hashlib.sha1(raw.encode()).hexdigest()[:20]
