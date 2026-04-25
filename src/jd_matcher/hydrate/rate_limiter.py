"""Process-wide thread-safe rate limiter for external HTTP calls."""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """Enforces a minimum interval between calls, process-wide.

    Thread-safe: concurrent callers serialize — each waits until the previous
    caller's interval has elapsed before returning.
    """

    def __init__(self, min_interval_sec: float) -> None:
        self._min_interval = min_interval_sec
        self._lock = threading.Lock()
        self._last_call_at: float | None = None

    def wait(self) -> None:
        """Block until min_interval has elapsed since the last call.

        The first call returns immediately.  Each subsequent call waits for
        the remaining interval since the previous call completed.
        """
        with self._lock:
            now = time.monotonic()
            if self._last_call_at is not None:
                elapsed = now - self._last_call_at
                remaining = self._min_interval - elapsed
                if remaining > 0:
                    time.sleep(remaining)
            self._last_call_at = time.monotonic()


# Single global hydration rate limiter — 1 request per 30 seconds across all sources
# combined per TDD §C5 contract.
HYDRATOR_RATE_LIMITER = RateLimiter(min_interval_sec=30.0)
