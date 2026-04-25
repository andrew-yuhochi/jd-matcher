"""JD Hydrator — fetches full job descriptions from public guest endpoints."""

from __future__ import annotations

from typing import Literal

from jd_matcher.hydrate.linkedin import HydratedJD


def compute_source_health(
    results: list[HydratedJD],
) -> tuple[Literal["healthy", "degraded", "failed"], str | None]:
    """Compute source-level health from a batch of hydration results.

    Returns a (health_status, failure_reason) tuple.  failure_reason is None
    when health_status is 'healthy'.

    Thresholds:
        0%        failed  → healthy,  failure_reason=None
        0–20%     failed  → healthy,  failure_reason=None
        20–100%   failed  → degraded, failure_reason='partial_hydration_failure_rate'
        100%      failed  → failed,   failure_reason='rate_limit' if all HTTP 429
                                      else dominant exception text
    """
    if not results:
        return "healthy", None

    n_total = len(results)
    n_failed = sum(1 for r in results if r.hydration_status == "failed")
    fail_rate = n_failed / n_total

    if fail_rate == 0.0:
        return "healthy", None

    if fail_rate <= 0.20:
        return "healthy", None

    if fail_rate < 1.0:
        return "degraded", "partial_hydration_failure_rate"

    # 100% failure — determine reason
    all_429 = all(
        r.failure_reason is not None and "429" in (r.failure_reason or "")
        for r in results
        if r.hydration_status == "failed"
    )
    if all_429:
        return "failed", "rate_limit"

    last_reason = next(
        (r.failure_reason for r in reversed(results) if r.hydration_status == "failed"),
        "unknown",
    )
    return "failed", last_reason
