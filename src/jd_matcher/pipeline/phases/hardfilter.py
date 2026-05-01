"""Phase: hardfilter — Hard filter on LLM-extracted canonical fields (C33).

STUB — implemented at TASK-M3-006.

Writes a 'hardfilter' pipeline_runs row with health_status='healthy' and
counts={filtered:0, unfiltered:0} so the mandatory-persistence invariant
(C11: exactly one row per source per run) holds from M3 onward.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def run(
    *,
    run_id: str,
    resolved_db: Path,
    started_at: datetime,
    logger: logging.Logger,
    write_pipeline_run: Callable,
) -> dict:
    """Stub hardfilter phase — no-op pass-through until TASK-M3-006."""
    write_pipeline_run(
        resolved_db,
        run_id=run_id,
        source="hardfilter",
        health_status="healthy",
        failure_reason=None,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        last_successful_fetch_at=datetime.now(timezone.utc),
        counts={"filtered": 0, "unfiltered": 0, "filter_reasons": {}},
    )
    return {"filtered": 0, "unfiltered": 0}
