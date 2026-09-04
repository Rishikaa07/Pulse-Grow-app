"""Background refresh.

An asyncio task, not a microservice and not Celery. It has exactly one job:
keep the shared market snapshot warm so that no user request ever waits on a
provider, and archive the tape periodically.

Why this is enough at this size, and how it grows: the loop is idempotent and
holds no state, so running N replicas is safe today (they duplicate work) and
becomes efficient the moment the cache is Redis and the loop takes a short
lock. Nothing above it changes when that happens.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from .config import settings
from .db.session import session_scope
from .repositories.events import ChangeEventRepository
from .repositories.snapshots import MarketSnapshotRepository, VisitRepository
from .services.market import market_service

log = logging.getLogger(__name__)

ARCHIVE_EVERY_N_CYCLES = 10
RETENTION_EVERY_N_CYCLES = 240


class RefreshWorker:
    def __init__(self, interval_s: int | None = None) -> None:
        self.interval_s = interval_s or settings.refresh_interval_s
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.cycles = 0
        self.failures = 0
        self.last_run: datetime | None = None

    async def start(self) -> None:
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="pulse-refresh")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown path
                pass

    async def _run(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.to_thread(self._cycle)
                self.failures = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed background job must never take the API with it.
                self.failures += 1
                log.exception("refresh cycle failed (%s consecutive)", self.failures)

            # Back off after repeated failures instead of hammering a sick feed.
            delay = self.interval_s * min(8, 2**self.failures) if self.failures else self.interval_s
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=delay)
            except TimeoutError:
                continue

    def _cycle(self) -> None:
        snapshot = market_service.snapshot(force=True)
        self.cycles += 1
        self.last_run = datetime.now(UTC)

        if self.cycles % ARCHIVE_EVERY_N_CYCLES == 0 and snapshot.quotes:
            with session_scope() as db:
                MarketSnapshotRepository(db).record_many(
                    [
                        {
                            "symbol": q.symbol,
                            "price": q.price,
                            "volume": q.volume,
                            "source": q.quality.selected_source,
                            "freshness": q.quality.freshness,
                            "captured_at": q.as_of,
                        }
                        for q in snapshot.quotes.values()
                    ]
                )

        if self.cycles % RETENTION_EVERY_N_CYCLES == 0:
            with session_scope() as db:
                removed = MarketSnapshotRepository(db).prune()
                removed += ChangeEventRepository(db).prune()
                removed += VisitRepository(db).prune_visits()
                log.info("retention pass removed %s rows", removed)


worker = RefreshWorker()
