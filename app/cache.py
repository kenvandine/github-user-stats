import asyncio
import time
from typing import Any


class TTLCache:
    """In-memory TTL cache with stale-serving support."""

    MIN_TTL = 1800  # 30 minutes minimum

    def __init__(self, default_ttl: int = 1800):
        self._store: dict[str, tuple[Any, float]] = {}  # key -> (value, expiry)
        self._default_ttl = max(default_ttl, self.MIN_TTL)
        self._cleanup_task: asyncio.Task | None = None

    def get(self, key: str) -> Any | None:
        """Return cached value if not expired, else None."""
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if time.monotonic() > expiry:
            # Lazy eviction
            del self._store[key]
            return None
        return value

    def get_with_stale(self, key: str) -> tuple[Any | None, bool]:
        """Return (value, is_stale). Returns expired entries as fallback."""
        entry = self._store.get(key)
        if entry is None:
            return None, False
        value, expiry = entry
        is_stale = time.monotonic() > expiry
        return value, is_stale

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        """Store a value with TTL."""
        effective_ttl = max(ttl or self._default_ttl, self.MIN_TTL)
        self._store[key] = (value, time.monotonic() + effective_ttl)

    def _cleanup(self) -> None:
        """Remove all expired entries."""
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._store.items() if now > exp]
        for k in expired:
            del self._store[k]

    async def start_cleanup_loop(self, interval: int = 300) -> None:
        """Background cleanup every `interval` seconds (default 5 min)."""
        while True:
            await asyncio.sleep(interval)
            self._cleanup()

    def start_background_cleanup(self) -> None:
        """Start the background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self.start_cleanup_loop())


# Module-level singleton
stats_cache = TTLCache()
