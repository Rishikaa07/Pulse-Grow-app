"""Application configuration.

Everything tunable lives here so that behaviour is configured, never hardcoded
in the middle of a request handler. Values are read from the environment once
at import time.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class FreshnessPolicy:
    """Age thresholds (seconds) that map a quote timestamp to a freshness state."""

    fresh_max_age_s: int = 60
    delayed_max_age_s: int = 900
    stale_max_age_s: int = 3600  # beyond this a quote is treated as unavailable

    def classify(self, age_seconds: float) -> str:
        if age_seconds <= self.fresh_max_age_s:
            return "fresh"
        if age_seconds <= self.delayed_max_age_s:
            return "delayed"
        if age_seconds <= self.stale_max_age_s:
            return "stale"
        return "unavailable"


@dataclass(frozen=True)
class Settings:
    app_name: str = "Pulse"
    environment: str = field(default_factory=lambda: _env("PULSE_ENV", "development"))
    secret_key: str = field(default_factory=lambda: _env("PULSE_SECRET_KEY", "dev-only-insecure-key"))

    database_url: str = field(
        default_factory=lambda: _env("DATABASE_URL", "sqlite:///./pulse.db")
    )
    redis_url: str | None = field(default_factory=lambda: os.environ.get("REDIS_URL"))

    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in _env("CORS_ORIGINS", "http://localhost:3000").split(",")
            if o.strip()
        )
    )

    # --- session / visit semantics -------------------------------------------------
    session_ttl_days: int = field(default_factory=lambda: _env_int("SESSION_TTL_DAYS", 30))
    # A visit is considered finished after this much inactivity. The next request
    # then opens a NEW visit, and the baseline for "since your last check" becomes
    # whatever the user last actually saw. This is what makes the product honest.
    visit_idle_timeout_s: int = field(
        default_factory=lambda: _env_int("VISIT_IDLE_TIMEOUT_S", 900)
    )

    # --- market data ---------------------------------------------------------------
    quote_cache_ttl_s: int = field(default_factory=lambda: _env_int("QUOTE_CACHE_TTL_S", 20))
    history_cache_ttl_s: int = field(default_factory=lambda: _env_int("HISTORY_CACHE_TTL_S", 900))
    provider_timeout_s: float = field(default_factory=lambda: _env_float("PROVIDER_TIMEOUT_S", 2.5))
    # Two providers disagreeing by more than this fraction is a reconciliation event.
    provider_price_tolerance: float = field(
        default_factory=lambda: _env_float("PROVIDER_PRICE_TOLERANCE", 0.004)
    )
    refresh_interval_s: int = field(default_factory=lambda: _env_int("REFRESH_INTERVAL_S", 30))
    max_symbols_per_watchlist: int = field(
        default_factory=lambda: _env_int("MAX_SYMBOLS_PER_WATCHLIST", 60)
    )

    freshness: FreshnessPolicy = field(default_factory=FreshnessPolicy)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
