from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: defaultdict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.RLock()

    def allows(self, *keys: str) -> bool:
        with self._lock:
            now = time.monotonic()
            oldest_allowed = now - self.window_seconds
            for key in keys:
                hits = self._hits[key]
                while hits and hits[0] <= oldest_allowed:
                    hits.popleft()
            if any(len(self._hits[key]) >= self.limit for key in keys):
                return False
            for key in keys:
                self._hits[key].append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
