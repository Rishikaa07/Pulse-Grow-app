"""Cache layer.

Market data is shared, not per-user: a hundred people watching NVDA must cause
one upstream fetch, not a hundred. That is the entire reason this exists.

The in-memory backend is the default so the project runs with no infrastructure.
Setting REDIS_URL swaps in Redis and the cache becomes shared across processes —
the interface does not change, so nothing above it has to care.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from typing import Any

from .config import settings

log = logging.getLogger(__name__)


class Cache(ABC):
    @abstractmethod
    def get(self, key: str) -> Any | None: ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl_s: int) -> None: ...

    @abstractmethod
    def delete_prefix(self, prefix: str) -> None: ...

    def get_or_set(self, key: str, ttl_s: int, factory) -> Any:
        hit = self.get(key)
        if hit is not None:
            return hit
        value = factory()
        if value is not None:
            self.set(key, value, ttl_s)
        return value


class InMemoryCache(Cache):
    """Process-local TTL cache. Thread-safe; the refresh loop writes to it."""

    def __init__(self, max_entries: int = 4096) -> None:
        self._data: dict[str, tuple[float, Any]] = {}
        self._lock = threading.RLock()
        self._max = max_entries

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < time.monotonic():
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl_s: int) -> None:
        with self._lock:
            if len(self._data) >= self._max:
                # Cheap eviction: drop everything already expired, then the oldest.
                now = time.monotonic()
                for k in [k for k, (exp, _) in self._data.items() if exp < now]:
                    self._data.pop(k, None)
                if len(self._data) >= self._max:
                    oldest = min(self._data, key=lambda k: self._data[k][0])
                    self._data.pop(oldest, None)
            self._data[key] = (time.monotonic() + ttl_s, value)

    def delete_prefix(self, prefix: str) -> None:
        with self._lock:
            for key in [k for k in self._data if k.startswith(prefix)]:
                self._data.pop(key, None)


class RedisCache(Cache):
    def __init__(self, url: str) -> None:
        import redis  # imported lazily so redis stays an optional dependency

        self._client = redis.Redis.from_url(url, socket_timeout=1.0)
        self._prefix = "pulse:"

    def get(self, key: str) -> Any | None:
        try:
            raw = self._client.get(self._prefix + key)
        except Exception as exc:  # a cache outage must never be a page outage
            log.warning("redis get failed: %s", exc)
            return None
        return json.loads(raw) if raw else None

    def set(self, key: str, value: Any, ttl_s: int) -> None:
        try:
            self._client.setex(self._prefix + key, ttl_s, json.dumps(value, default=str))
        except Exception as exc:
            log.warning("redis set failed: %s", exc)

    def delete_prefix(self, prefix: str) -> None:
        try:
            for key in self._client.scan_iter(match=f"{self._prefix}{prefix}*", count=500):
                self._client.delete(key)
        except Exception as exc:
            log.warning("redis purge failed: %s", exc)


def build_cache() -> Cache:
    if settings.redis_url:
        try:
            cache = RedisCache(settings.redis_url)
            log.info("cache backend: redis")
            return cache
        except Exception as exc:
            log.warning("redis unavailable (%s); falling back to in-memory cache", exc)
    log.info("cache backend: in-memory")
    return InMemoryCache()


cache: Cache = build_cache()
