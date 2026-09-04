"""Scoring configuration.

Every constant the engine uses lives here. Nothing in the engine is a magic
number defined at its call site, and a user can override the profile from
Settings — which is stored on the user row and passed into the engine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace


@dataclass(frozen=True)
class AttentionWeights:
    """Maximum points each signal can contribute.

    The maxima intentionally sum above 100: a stock must light up on several
    independent axes to saturate the score, so a single loud signal cannot
    dominate the feed.
    """

    price_move: float = 30.0
    volume_anomaly: float = 22.0
    sector_outperformance: float = 20.0
    market_outperformance: float = 12.0
    historical_unusualness: float = 12.0
    event: float = 10.0
    missed_while_away: float = 6.0

    # --- shape parameters ----------------------------------------------------
    #: Sigma multiple at which the price signal is ~85% saturated.
    price_sigma_scale: float = 1.6
    #: Relative volume where the volume signal starts, and where it saturates.
    volume_floor: float = 1.2
    volume_ceiling: float = 3.0
    #: Sigma multiple of benchmark-relative excess at which those signals max out.
    relative_sigma_ceiling: float = 2.5
    #: Percentile of the 90-day return distribution above which a move is "unusual".
    unusual_percentile_floor: float = 0.85

    # --- classification ------------------------------------------------------
    high_threshold: float = 65.0
    medium_threshold: float = 52.0
    low_threshold: float = 22.0
    #: A move must clear this many sigma (or the absolute floor) to count as a
    #: change worth telling the user about at all.
    change_sigma_floor: float = 0.75
    change_abs_floor_pct: float = 0.35

    def to_dict(self) -> dict[str, float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict | None) -> "AttentionWeights":
        base = cls()
        if not raw:
            return base
        known = {k: v for k, v in raw.items() if k in base.to_dict()}
        clean: dict[str, float] = {}
        for key, value in known.items():
            try:
                clean[key] = float(value)
            except (TypeError, ValueError):
                continue
        return replace(base, **clean) if clean else base


DEFAULT_WEIGHTS = AttentionWeights()


PRESETS: dict[str, AttentionWeights] = {
    "balanced": DEFAULT_WEIGHTS,
    "price_first": AttentionWeights(
        price_move=40.0, volume_anomaly=14.0, sector_outperformance=16.0
    ),
    "relative_first": AttentionWeights(
        price_move=18.0,
        volume_anomaly=20.0,
        sector_outperformance=28.0,
        market_outperformance=18.0,
    ),
    "quiet": AttentionWeights(high_threshold=80.0, medium_threshold=58.0, low_threshold=32.0),
}
