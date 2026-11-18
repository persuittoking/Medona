"""In-memory sliding-window rate limiter (single process; enough for the hosted demo).

Used for POST /api/auth/login: LOGIN_RATE_LIMIT attempts per client IP per LOGIN_RATE_WINDOW_S seconds.
A multi-instance production deployment would move this to a shared store (e.g. Redis).
"""
import threading
import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window_s: float, now: float | None = None) -> bool:
        """Record one attempt for `key`; False if it would exceed `limit` attempts in the last `window_s` seconds.
        limit <= 0 disables the limit."""
        if limit <= 0:
            return True
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window_s:
                q.popleft()
            if len(q) >= limit:
                return False
            q.append(now)
            return True

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


login_limiter = SlidingWindowLimiter()
