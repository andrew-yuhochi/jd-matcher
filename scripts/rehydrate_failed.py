"""One-shot re-hydration for postings with hydration_status='failed'.

Skips Indeed-source postings (deferred to MVP per ALIGNMENT-LOG 2026-04-28).
LinkedIn-only. Rate limiter in linkedin.hydrate() applies; expect ~10 min for ~20 URLs.

Usage:
    .venv/bin/python scripts/rehydrate_failed.py
"""
import logging
import sqlite3
from pathlib import Path

from jd_matcher.hydrate.linkedin import hydrate as linkedin_hydrate

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"


def main() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    failed = conn.execute(
        """
        SELECT p.id AS posting_id, ps.source, ps.source_url
        FROM postings p
        JOIN posting_sources ps ON ps.posting_id = p.id
        WHERE p.hydration_status = 'failed'
        """
    ).fetchall()

    logger.info("Re-hydrating %d failed postings...", len(failed))

    ok_count = 0
    skip_count = 0
    still_failed = 0

    for row in failed:
        source = row["source"] or ""
        posting_id = row["posting_id"]
        url = row["source_url"]

        if "indeed" in source.lower():
            logger.info("  #%s: Indeed source — skipped (deferred to MVP)", posting_id)
            skip_count += 1
            continue

        logger.info("  #%s: re-hydrating LinkedIn URL %s", posting_id, url)
        try:
            result = linkedin_hydrate(url)
        except Exception as exc:
            logger.warning("  #%s: exception during hydration: %s", posting_id, exc)
            still_failed += 1
            continue

        if result.hydration_status == "complete":
            conn.execute(
                "UPDATE postings SET full_jd=?, hydration_status='complete' WHERE id=?",
                (result.description or "", posting_id),
            )
            conn.commit()
            logger.info("  #%s: OK", posting_id)
            ok_count += 1
        else:
            logger.warning(
                "  #%s: still %s — %s",
                posting_id,
                result.hydration_status,
                result.failure_reason,
            )
            still_failed += 1

    remaining = conn.execute(
        "SELECT count(*) FROM postings WHERE hydration_status='failed'"
    ).fetchone()[0]

    logger.info(
        "Done. OK=%d  skipped(Indeed)=%d  still-failed=%d  DB remaining-failed=%d",
        ok_count,
        skip_count,
        still_failed,
        remaining,
    )
    conn.close()


if __name__ == "__main__":
    main()
