"""
Gmail ingester — fetches raw RFC-822 email messages per sender.

SKIP_LIVE=1 bypasses live Gmail and reads from tests/fixtures/gmail/<sender>/*.eml
instead, enabling development and CI without OAuth credentials.

Failure contract (non-hideable, per TDD §C3):
  - Every per-sender fetch is wrapped in try/except.
  - On exception: writes pipeline_runs row with health_status='failed',
    returns []. Never re-raises.
  - On success: writes pipeline_runs row with health_status='healthy'.
"""

from __future__ import annotations

import base64
import email
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from email.header import decode_header, make_header
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

# Canonical sender-filter strings sourced from config/saved-searches.yaml
_SENDER_FILTERS: dict[str, str] = {
    "linkedin": "from:jobalerts-noreply@linkedin.com",
    "indeed": "from:alert@indeed.com",
}

# Maps short sender name to the fixture subdirectory name (same here, but
# explicit so a future mismatch is visible at the config level).
_FIXTURE_DIRS: dict[str, str] = {
    "linkedin": "linkedin",
    "indeed": "indeed",
}

# Resolved once at import time so tests can patch it.
_FIXTURES_ROOT = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "gmail"


@dataclass
class RawEmail:
    """Minimal envelope around a raw RFC-822 message body."""

    id: str
    sender: str
    subject: str
    received_at: datetime
    body_bytes: bytes


class GmailIngester:
    """Fetch raw emails from Gmail, one sender at a time.

    Args:
        credentials: A valid :class:`google.oauth2.credentials.Credentials`
            object.  May be ``None`` when ``SKIP_LIVE=1`` is set.
        db_path:     Path to the SQLite database (for pipeline_runs writes).
    """

    def __init__(self, credentials: Any, db_path: Path) -> None:
        self._credentials = credentials
        self._db_path = db_path
        self._service: Any = None  # lazily built

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fetch_for_sender(
        self,
        sender_filter: str,
        since_date: datetime,
        run_id: str | None = None,
    ) -> list[RawEmail]:
        """Fetch all emails matching *sender_filter* received after *since_date*.

        Args:
            sender_filter: Short name key ("linkedin" or "indeed") **or** the
                full Gmail query string (``from:…``).  Short-name keys are
                resolved via the internal lookup table.
            since_date:    Lower bound on message recency.  The Gmail query
                           uses ``newer_than:Nd`` derived from this date.
            run_id:        Caller-supplied idempotency key.  Defaults to a
                           random UUID prefixed with ``manual-``.

        Returns:
            A list of :class:`RawEmail` objects, or ``[]`` on any failure.
        """
        if run_id is None:
            run_id = f"manual-{uuid4()}"

        # Resolve the short name to the full filter string.
        sender_short = sender_filter
        if sender_filter in _SENDER_FILTERS:
            gmail_query_prefix = _SENDER_FILTERS[sender_filter]
        else:
            # Treat as a raw query; derive a short name for source column.
            gmail_query_prefix = sender_filter
            sender_short = sender_filter.replace("from:", "").split("@")[0].replace("-noreply", "")

        source_name = f"gmail_{sender_short}"
        started_at = datetime.now(timezone.utc)

        try:
            if os.environ.get("SKIP_LIVE") == "1":
                emails = self._fetch_from_fixtures(sender_short, since_date)
            else:
                emails = self._fetch_from_gmail(gmail_query_prefix, since_date)

            finished_at = datetime.now(timezone.utc)
            self._write_pipeline_run(
                run_id=run_id,
                source=source_name,
                health_status="healthy",
                failure_reason=None,
                started_at=started_at,
                finished_at=finished_at,
                last_successful_fetch_at=started_at,
            )
            logger.info(
                "fetch_for_sender: source=%s fetched=%d run_id=%s",
                source_name,
                len(emails),
                run_id,
            )
            return emails

        except Exception as exc:  # noqa: BLE001
            finished_at = datetime.now(timezone.utc)
            failure_reason = f"{type(exc).__name__}: {exc}"
            logger.error(
                "fetch_for_sender failed: source=%s reason=%s run_id=%s",
                source_name,
                failure_reason,
                run_id,
            )

            # Carry forward the most recent successful fetch timestamp so the
            # UI sub-bar can render a stale indicator with a known last-good time.
            last_successful = self._last_successful_fetch_at(source_name)

            self._write_pipeline_run(
                run_id=run_id,
                source=source_name,
                health_status="failed",
                failure_reason=failure_reason,
                started_at=started_at,
                finished_at=finished_at,
                last_successful_fetch_at=last_successful,
            )
            return []

    # ------------------------------------------------------------------
    # Gmail API path
    # ------------------------------------------------------------------

    def _build_service(self) -> Any:
        if self._service is None:
            from googleapiclient.discovery import build  # type: ignore[import-untyped]

            self._service = build("gmail", "v1", credentials=self._credentials)
        return self._service

    def _fetch_from_gmail(
        self, gmail_query_prefix: str, since_date: datetime
    ) -> list[RawEmail]:
        """Call Gmail API: messages.list + messages.get(format='raw')."""
        service = self._build_service()

        age_days = max(1, (datetime.now(timezone.utc) - since_date).days + 1)
        query = f"{gmail_query_prefix} newer_than:{age_days}d"
        logger.debug("Gmail query: %s", query)

        message_ids: list[str] = []
        page_token: str | None = None

        while True:
            kwargs: dict[str, Any] = {"userId": "me", "q": query}
            if page_token:
                kwargs["pageToken"] = page_token
            result = service.users().messages().list(**kwargs).execute()
            for msg in result.get("messages", []):
                message_ids.append(msg["id"])
            page_token = result.get("nextPageToken")
            if not page_token:
                break

        logger.debug("Gmail: %d message IDs matched query", len(message_ids))

        emails: list[RawEmail] = []
        for msg_id in message_ids:
            raw_msg = (
                service.users().messages().get(userId="me", id=msg_id, format="raw").execute()
            )
            body_bytes = base64.urlsafe_b64decode(raw_msg["raw"] + "==")
            parsed = email.message_from_bytes(body_bytes)
            sender = _decode_header_value(parsed.get("From", ""))
            subject = _decode_header_value(parsed.get("Subject", ""))
            date_str = parsed.get("Date", "")
            received_at = _parse_email_date(date_str)
            emails.append(
                RawEmail(
                    id=msg_id,
                    sender=sender,
                    subject=subject,
                    received_at=received_at,
                    body_bytes=body_bytes,
                )
            )

        return emails

    # ------------------------------------------------------------------
    # Fixture path (SKIP_LIVE=1)
    # ------------------------------------------------------------------

    def _fetch_from_fixtures(
        self, sender_short: str, since_date: datetime
    ) -> list[RawEmail]:
        """Read *.eml files from tests/fixtures/gmail/<sender_short>/."""
        fixture_dir_name = _FIXTURE_DIRS.get(sender_short, sender_short)
        fixture_dir = _FIXTURES_ROOT / fixture_dir_name

        if not fixture_dir.exists():
            raise FileNotFoundError(
                f"Fixture directory not found: {fixture_dir}. "
                "Create synthetic .eml files under tests/fixtures/gmail/<sender>/."
            )

        eml_files = sorted(fixture_dir.glob("*.eml"))
        if not eml_files:
            logger.warning("No .eml fixture files found in %s", fixture_dir)
            return []

        emails: list[RawEmail] = []
        for path in eml_files:
            body_bytes = path.read_bytes()
            parsed = email.message_from_bytes(body_bytes)
            sender = _decode_header_value(parsed.get("From", ""))
            subject = _decode_header_value(parsed.get("Subject", ""))
            date_str = parsed.get("Date", "")
            received_at = _parse_email_date(date_str)
            emails.append(
                RawEmail(
                    id=path.stem,
                    sender=sender,
                    subject=subject,
                    received_at=received_at,
                    body_bytes=body_bytes,
                )
            )
            logger.debug("Loaded fixture: %s — subject=%r sender=%r", path.name, subject, sender)

        return emails

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _write_pipeline_run(
        self,
        *,
        run_id: str,
        source: str,
        health_status: str,
        failure_reason: str | None,
        started_at: datetime,
        finished_at: datetime,
        last_successful_fetch_at: datetime | None,
    ) -> None:
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """
                INSERT INTO pipeline_runs
                    (run_id, source, health_status, failure_reason,
                     started_at, finished_at, last_successful_fetch_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    source,
                    health_status,
                    failure_reason,
                    started_at.isoformat(),
                    finished_at.isoformat(),
                    last_successful_fetch_at.isoformat() if last_successful_fetch_at else None,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _last_successful_fetch_at(self, source: str) -> datetime | None:
        """Return the most recent healthy fetch timestamp for *source*, or None."""
        conn = sqlite3.connect(self._db_path)
        try:
            row = conn.execute(
                """
                SELECT last_successful_fetch_at
                FROM pipeline_runs
                WHERE source = ? AND health_status = 'healthy'
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (source,),
            ).fetchone()
            if row and row[0]:
                return datetime.fromisoformat(row[0])
            return None
        finally:
            conn.close()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _decode_header_value(raw: object) -> str:
    """Decode a possibly-encoded email header value to a plain string."""
    if raw is None:
        return ""
    if not isinstance(raw, str):
        # email.header.Header object — convert via make_header round-trip
        try:
            return str(make_header(decode_header(str(raw))))
        except Exception:  # noqa: BLE001
            return str(raw)
    try:
        return str(make_header(decode_header(raw)))
    except Exception:  # noqa: BLE001
        return raw


def _parse_email_date(date_str: str) -> datetime:
    """Parse an RFC-2822 Date header to a UTC-aware datetime.

    Falls back to UTC now on parse failure so callers always get a valid value.
    """
    if not date_str:
        return datetime.now(timezone.utc)
    from email.utils import parsedate_to_datetime

    try:
        dt = parsedate_to_datetime(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        logger.warning("Could not parse email Date header %r — using now(UTC)", date_str)
        return datetime.now(timezone.utc)
