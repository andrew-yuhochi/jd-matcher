"""
Gmail OAuth 2.0 loopback flow.

First-run: opens browser, captures auth code, exchanges for tokens, persists
refresh token to token_path with chmod 600.
Subsequent runs: loads and refreshes tokens silently.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class OAuthTokenInvalid(Exception):
    """Raised when the stored OAuth token cannot be refreshed (revoked or expired)."""


def get_credentials(client_path: Path, token_path: Path) -> Credentials:
    """Load stored credentials or run the loopback consent flow on first use.

    Persists a refreshed or newly-obtained token to *token_path* with
    mode 0o600 so the refresh token is not world-readable.

    Args:
        client_path: Path to the GCP OAuth client secrets JSON.
        token_path:  Path where the token JSON is stored (created on first run).

    Returns:
        A valid :class:`google.oauth2.credentials.Credentials` object.

    Raises:
        OAuthTokenInvalid: When an existing token cannot be refreshed
            (revoked refresh token or app status change).
    """
    creds: Credentials | None = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as exc:
            logger.error("OAuth token refresh failed — re-authorization required: %s", exc)
            raise OAuthTokenInvalid(
                "Stored OAuth token is invalid or revoked. "
                "Run `python -m jd_matcher.auth` to re-authorize."
            ) from exc

    if not creds or not creds.valid:
        creds = _run_loopback_flow(client_path)

    _persist_token(creds, token_path)
    return creds


def _run_loopback_flow(client_path: Path) -> Credentials:
    """Run the OAuth loopback redirect flow on an ephemeral local port."""
    flow = InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)
    creds = flow.run_local_server(port=0)
    return creds


def _persist_token(creds: Credentials, token_path: Path) -> None:
    """Write credentials JSON and tighten file permissions to 0o600."""
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)
    logger.debug("OAuth token persisted to %s", token_path)
