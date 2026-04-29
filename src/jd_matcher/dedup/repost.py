"""C30 — Repost Detector.

Public API:
    detect_repost(decision, candidate_first_seen, db_path=None) -> DedupDecision

Standalone predicate: given a DedupDecision with action='merge', checks whether
the candidate posting is a repost of the target canonical.

Repost criterion (TDD §C30):
    candidate.first_seen >= MAX(posting_canonical_links.merged_at
                                WHERE canonical_id = <target>) + 30 days

When the criterion is met:
  - Retags decision.merge_kind from 'content_dedup' → 'repost'
  - Emits posting_reposted event via C10 (events table)
  - The merge still happens — repost is an analytical distinction, not routing

Inactive/Expired invariant: by the time C30 sees a decision, C21 has already
filtered Inactive/Expired canonicals.  A posting whose true match was
Inactive/Expired arrives as action='new'; C30 is a no-op for action='new'.

First-deployment edge: if no prior posting_canonical_links row exists
(impossible by design — canonicals are created with their seed link), C30
returns the input unchanged.

Threshold configurable via config/dedup.yaml: dedup.repost_threshold_days (default 30).
"""

from __future__ import annotations

import json
import logging
import sqlite3
import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jd_matcher.dedup.engine import DedupDecision

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"
_DEFAULT_DEDUP_CONFIG_PATH = Path(__file__).parents[3] / "config" / "dedup.yaml"
_DEFAULT_REPOST_THRESHOLD_DAYS = 30


def _load_repost_threshold(config_path: Path | None = None) -> int:
    resolved = config_path or _DEFAULT_DEDUP_CONFIG_PATH
    if not resolved.exists():
        return _DEFAULT_REPOST_THRESHOLD_DAYS
    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
        return int(raw.get("dedup", {}).get("repost_threshold_days", _DEFAULT_REPOST_THRESHOLD_DAYS))
    except Exception as exc:
        logger.warning("repost config parse error (%s) — using default %d days", exc, _DEFAULT_REPOST_THRESHOLD_DAYS)
        return _DEFAULT_REPOST_THRESHOLD_DAYS


def _emit_repost_event(
    *,
    canonical_id: int,
    candidate_posting_id: int,
    days_since_last_link: float,
    previous_link_merged_at: str,
    user_id: str,
    db_path: Path,
) -> None:
    """Write posting_reposted event to the events table (C10 contract)."""
    metadata = json.dumps(
        {
            "canonical_id": canonical_id,
            "candidate_posting_id": candidate_posting_id,
            "days_since_last_link": round(days_since_last_link, 2),
            "previous_link_merged_at": previous_link_merged_at,
        }
    )
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO events (user_id, event_type, posting_id, metadata, timestamp)
            VALUES (?, 'posting_reposted', ?, ?, ?)
            """,
            (user_id, candidate_posting_id, metadata, now),
        )
        conn.commit()
        logger.info(
            "C30 repost event emitted: canonical_id=%d posting_id=%d days=%.1f",
            canonical_id,
            candidate_posting_id,
            days_since_last_link,
        )
    except Exception as exc:
        # Event emission failure is Minor-tier (C10 contract: event drop acceptable;
        # the merge itself must not fail due to event emission problems).
        logger.warning(
            "C30 event emission failed (posting_id=%d canonical_id=%d): %s",
            candidate_posting_id,
            canonical_id,
            exc,
        )
    finally:
        conn.close()


def detect_repost(
    decision: DedupDecision,
    candidate_id: int,
    db_path: Path | None = None,
    config_path: Path | None = None,
) -> DedupDecision:
    """Check whether the candidate is a repost of the target canonical.

    For action='new' decisions, returns the decision unchanged (no-op).
    For action='merge', queries posting_canonical_links for the most recent
    prior link and applies the 30-day threshold.

    Args:
        decision:     Output of C21's decide().
        candidate_id: posting_id of the candidate posting.
        db_path:      Path to SQLite DB; defaults to ~/.jd-matcher/jd-matcher.db.
        config_path:  Path to dedup.yaml; defaults to config/dedup.yaml.

    Returns:
        Possibly-retagged DedupDecision (merge_kind='repost' if criterion met).
    """
    if decision.action != "merge":
        # action='new': C30 is a no-op pass-through (TDD §C30 resp. 5)
        return decision

    resolved_db = db_path or _DEFAULT_DB_PATH
    canonical_id = decision.target_canonical_id
    if canonical_id is None:
        return decision

    threshold_days = _load_repost_threshold(config_path)

    conn = sqlite3.connect(resolved_db)
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        # Find MAX(merged_at) across all prior links for this canonical
        row = conn.execute(
            """
            SELECT MAX(merged_at)
            FROM posting_canonical_links
            WHERE canonical_id = ?
            """,
            (canonical_id,),
        ).fetchone()

        if row is None or row[0] is None:
            # No prior links found (impossible by design per TDD §C30 resp. 5)
            logger.debug(
                "C30: no prior links for canonical_id=%d — returning unchanged",
                canonical_id,
            )
            return decision

        last_merged_at_str: str = row[0]

        # Fetch candidate's first_seen timestamp
        posting_row = conn.execute(
            "SELECT first_seen, user_id FROM postings WHERE id = ?",
            (candidate_id,),
        ).fetchone()
        if posting_row is None:
            logger.warning("C30: posting %d not found — returning unchanged", candidate_id)
            return decision

        candidate_first_seen_str, user_id = posting_row
        user_id = user_id or "default"

        # Parse timestamps — handle both with-tz and naive ISO strings
        def _parse_ts(s: str) -> datetime:
            if s.endswith("Z"):
                s = s[:-1] + "+00:00"
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

        last_merged_at = _parse_ts(last_merged_at_str)
        candidate_first_seen = _parse_ts(candidate_first_seen_str)

        repost_boundary = last_merged_at + timedelta(days=threshold_days)
        days_since_last_link = (candidate_first_seen - last_merged_at).total_seconds() / 86400

        logger.debug(
            "C30: posting_id=%d canonical_id=%d candidate_first_seen=%s "
            "last_merged_at=%s boundary=%s days=%.1f threshold=%d",
            candidate_id,
            canonical_id,
            candidate_first_seen_str,
            last_merged_at_str,
            repost_boundary.isoformat(),
            days_since_last_link,
            threshold_days,
        )

        if candidate_first_seen >= repost_boundary:
            logger.info(
                "C30: REPOST detected posting_id=%d canonical_id=%d days=%.1f",
                candidate_id,
                canonical_id,
                days_since_last_link,
            )
            _emit_repost_event(
                canonical_id=canonical_id,
                candidate_posting_id=candidate_id,
                days_since_last_link=days_since_last_link,
                previous_link_merged_at=last_merged_at_str,
                user_id=user_id,
                db_path=resolved_db,
            )
            # Retag: build new DedupDecision with merge_kind='repost'
            return DedupDecision(
                action=decision.action,
                target_canonical_id=decision.target_canonical_id,
                similarity=decision.similarity,
                merge_kind="repost",
                stage1_block_size=decision.stage1_block_size,
                stage2_top_match_score=decision.stage2_top_match_score,
                blocked_by=decision.blocked_by,
            )
        else:
            # Within the repost window: not a repost
            return decision

    finally:
        conn.close()
