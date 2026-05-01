"""Phase: rank — Soft ranking of canonical postings (C34).

STUB — implemented at TASK-M3-007.

Writes a 'rank' pipeline_runs row with health_status='healthy' and
counts={ranked:0} so the mandatory-persistence invariant holds from M3 onward.
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
    """Stub rank phase — no-op pass-through until TASK-M3-007."""
    write_pipeline_run(
        resolved_db,
        run_id=run_id,
        source="rank",
        health_status="healthy",
        failure_reason=None,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        last_successful_fetch_at=datetime.now(timezone.utc),
        counts={"ranked": 0},
    )
    return {"ranked": 0}
