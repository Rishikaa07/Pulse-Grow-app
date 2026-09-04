"""Provider registry: fan out, reconcile, degrade gracefully.

Rules, in order:

1.  Ask every healthy provider. One failing feed must not take the page down.
2.  If two feeds agree within tolerance, use the highest-priority one and mark
    the quote corroborated.
3.  If they disagree beyond tolerance, still use the highest-priority one — but
    never silently. Record the discrepancy and attach it to the quote so the UI
    can show a data-quality badge and the engine can lower confidence.
4.  If every feed fails, serve the last known good quote from cache and label it
    stale. A stale number that is honestly labelled beats a blank screen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from ..config import settings
from .base import (
    HistoryPoint,
    MarketDataProvider,
    ProviderError,
    ProviderHealth,
    Quote,
    QuoteQuality,
    RawEvent,
    RawQuote,
)

log = logging.getLogger(__name__)


@dataclass
class Discrepancy:
    symbol: str
    primary_source: str
    primary_price: float
    other_source: str
    other_price: float
    deviation_pct: float
    detected_at: datetime


@dataclass
class QuoteBatch:
    quotes: dict[str, Quote]
    discrepancies: list[Discrepancy]
    provider_health: list[ProviderHealth]
    missing: list[str]
    degraded: bool


class ProviderRegistry:
    def __init__(self, providers: list[MarketDataProvider]) -> None:
        self._providers = sorted(providers, key=lambda p: p.priority)
        # Last known good quote per symbol — the safety net for total outage.
        self._last_good: dict[str, RawQuote] = {}

    @property
    def providers(self) -> list[MarketDataProvider]:
        return list(self._providers)

    # -- quotes ---------------------------------------------------------------

    def get_quotes(self, symbols: list[str]) -> QuoteBatch:
        wanted = [s.upper() for s in dict.fromkeys(symbols)]
        if not wanted:
            return QuoteBatch({}, [], [p.health() for p in self._providers], [], False)

        results: list[tuple[MarketDataProvider, dict[str, RawQuote]]] = []
        health: list[ProviderHealth] = []
        for provider in self._providers:
            try:
                results.append((provider, provider.get_quotes(wanted)))
                health.append(provider.health())
            except ProviderError as exc:
                log.warning("provider %s failed: %s", provider.name, exc)
                health.append(
                    ProviderHealth(provider.name, provider.priority, False, 0.0, str(exc))
                )
            except Exception as exc:  # a vendor SDK can raise literally anything
                log.exception("provider %s raised unexpectedly", provider.name)
                health.append(
                    ProviderHealth(provider.name, provider.priority, False, 0.0, repr(exc))
                )

        now = datetime.now(UTC)
        quotes: dict[str, Quote] = {}
        discrepancies: list[Discrepancy] = []
        missing: list[str] = []

        for symbol in wanted:
            candidates = [(p, batch[symbol]) for p, batch in results if symbol in batch]
            if candidates:
                quote, disc = self._reconcile(symbol, candidates, now)
                self._last_good[symbol] = candidates[0][1]
                quotes[symbol] = quote
                discrepancies.extend(disc)
                continue

            fallback = self._last_good.get(symbol)
            if fallback is None:
                missing.append(symbol)
                continue
            quotes[symbol] = self._as_quote(
                fallback,
                QuoteQuality(
                    freshness=settings.freshness.classify(
                        (now - fallback.as_of).total_seconds()
                    ),
                    age_seconds=(now - fallback.as_of).total_seconds(),
                    selected_source=f"{fallback.source} (cached)",
                    sources_agreeing=0,
                    sources_total=0,
                    notes=["All live feeds failed. Showing the last verified snapshot."],
                ),
            )

        degraded = any(not h.ok for h in health) or bool(missing)
        return QuoteBatch(quotes, discrepancies, health, missing, degraded)

    def _reconcile(
        self,
        symbol: str,
        candidates: list[tuple[MarketDataProvider, RawQuote]],
        now: datetime,
    ) -> tuple[Quote, list[Discrepancy]]:
        # candidates arrive in priority order because self._providers is sorted.
        _, chosen = candidates[0]
        tolerance = settings.provider_price_tolerance

        agreeing = 1
        worst: Discrepancy | None = None
        notes: list[str] = []

        for _, other in candidates[1:]:
            if chosen.price <= 0:
                continue
            deviation = abs(other.price - chosen.price) / chosen.price
            if deviation <= tolerance:
                agreeing += 1
                continue
            disc = Discrepancy(
                symbol=symbol,
                primary_source=chosen.source,
                primary_price=chosen.price,
                other_source=other.source,
                other_price=other.price,
                deviation_pct=round(deviation * 100, 4),
                detected_at=now,
            )
            if worst is None or disc.deviation_pct > worst.deviation_pct:
                worst = disc

        if worst is not None:
            notes.append(
                f"Feeds disagree by {worst.deviation_pct:.2f}%. "
                f"Using {chosen.source} (higher priority)."
            )

        age = (now - chosen.as_of).total_seconds()
        freshness = settings.freshness.classify(age)
        if freshness in {"stale", "unavailable"}:
            notes.append(f"{chosen.source} has not updated for {int(age // 60)} minutes.")

        quality = QuoteQuality(
            freshness=freshness,
            age_seconds=age,
            selected_source=chosen.source,
            sources_agreeing=agreeing,
            sources_total=len(candidates),
            discrepancy_pct=worst.deviation_pct if worst else None,
            notes=notes,
        )
        return self._as_quote(chosen, quality), ([worst] if worst else [])

    @staticmethod
    def _as_quote(raw: RawQuote, quality: QuoteQuality) -> Quote:
        return Quote(
            symbol=raw.symbol,
            price=raw.price,
            prev_close=raw.prev_close,
            open_price=raw.open_price,
            day_high=raw.day_high,
            day_low=raw.day_low,
            volume=raw.volume,
            as_of=raw.as_of,
            quality=quality,
        )

    # -- history & events -----------------------------------------------------

    def get_history(self, symbol: str, days: int = 90) -> list[HistoryPoint]:
        for provider in self._providers:
            try:
                points = provider.get_history(symbol, days)
                if points:
                    return points
            except ProviderError as exc:
                log.warning("history from %s failed: %s", provider.name, exc)
        return []

    def get_events(self, symbols: list[str]) -> list[RawEvent]:
        seen: set[str] = set()
        out: list[RawEvent] = []
        for provider in self._providers:
            try:
                for event in provider.get_events(symbols):
                    if event.id in seen:  # de-duplicate across feeds
                        continue
                    seen.add(event.id)
                    out.append(event)
            except ProviderError as exc:
                log.warning("events from %s failed: %s", provider.name, exc)
        out.sort(key=lambda e: e.occurred_at, reverse=True)
        return out

    def health(self) -> list[ProviderHealth]:
        out: list[ProviderHealth] = []
        for provider in self._providers:
            try:
                out.append(provider.health())
            except Exception as exc:
                out.append(ProviderHealth(provider.name, provider.priority, False, 0.0, repr(exc)))
        return out
