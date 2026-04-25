"""Tests for process-wide thread-safe rate limiter."""

from __future__ import annotations

import threading
import time

import pytest

from jd_matcher.hydrate.rate_limiter import RateLimiter


def test_first_call_does_not_block() -> None:
    """First wait() returns immediately (within 100ms tolerance)."""
    limiter = RateLimiter(min_interval_sec=30.0)
    start = time.monotonic()
    limiter.wait()
    elapsed = time.monotonic() - start
    assert elapsed < 0.1, f"First call took {elapsed:.3f}s — should be near-instant"


def test_subsequent_calls_block_for_min_interval() -> None:
    """Second wait() blocks approximately min_interval seconds."""
    interval = 0.5
    limiter = RateLimiter(min_interval_sec=interval)
    limiter.wait()  # first call — sets the clock
    start = time.monotonic()
    limiter.wait()  # second call — should block
    elapsed = time.monotonic() - start
    # Allow 20% tolerance: between 0.4s and 0.7s
    assert elapsed >= interval * 0.8, f"Did not block long enough: {elapsed:.3f}s"
    assert elapsed < interval * 1.5, f"Blocked too long: {elapsed:.3f}s"


def test_cross_source_serialization_via_shared_limiter() -> None:
    """A LinkedIn call immediately followed by an Indeed call serialize via the shared HYDRATOR_RATE_LIMITER."""
    from jd_matcher.hydrate.rate_limiter import HYDRATOR_RATE_LIMITER

    # First call on the shared limiter — no wait
    t0 = time.monotonic()
    HYDRATOR_RATE_LIMITER.wait()
    t1 = time.monotonic()
    assert t1 - t0 < 0.5, f"First call should not block; took {t1-t0:.3f}s"

    # Verify cross-source serialization with a short-interval fresh instance
    from jd_matcher.hydrate.rate_limiter import RateLimiter
    test_limiter = RateLimiter(min_interval_sec=0.5)
    test_limiter.wait()  # first call — no block
    t2 = time.monotonic()
    test_limiter.wait()  # second call — should block ~0.5s
    t3 = time.monotonic()
    assert t3 - t2 >= 0.4, f"Second call should block ~0.5s; took {t3-t2:.3f}s"


def test_concurrent_callers_serialize() -> None:
    """Two threads calling wait() serialize — second one waits for the interval."""
    interval = 0.5
    limiter = RateLimiter(min_interval_sec=interval)

    results: list[float] = []
    errors: list[Exception] = []

    def worker() -> None:
        try:
            start = time.monotonic()
            limiter.wait()
            results.append(time.monotonic() - start)
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)

    t1.start()
    # Small delay so t2 starts while t1 is holding the lock (or just after)
    time.sleep(0.01)
    t2.start()

    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not errors, f"Thread errors: {errors}"
    assert len(results) == 2

    # One thread should have completed quickly (first), the other ~interval
    results.sort()
    fast, slow = results
    # First through is near-instant (from its own perspective)
    assert fast < interval * 0.5, f"Fast thread took {fast:.3f}s — expected near-instant"
    # Second thread waited at least interval * 0.8
    assert slow >= interval * 0.8, f"Slow thread took {slow:.3f}s — expected ~{interval}s"
