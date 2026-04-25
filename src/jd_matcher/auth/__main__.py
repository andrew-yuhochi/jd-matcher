"""
CLI entry-point for first-run OAuth authorization.

Usage:
    python -m jd_matcher.auth

Opens the browser consent screen, exchanges the auth code for tokens, and
stores the refresh token at ~/.jd-matcher/tokens.json.  Subsequent pipeline
runs reuse this token silently.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from jd_matcher.auth.gmail_oauth import OAuthTokenInvalid, get_credentials

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_CLIENT_PATH = Path(
    os.environ.get("GMAIL_OAUTH_CLIENT_PATH", Path.home() / ".jd-matcher" / "credentials.json")
)
_DEFAULT_TOKEN_PATH = Path.home() / ".jd-matcher" / "tokens.json"


def main() -> None:
    client_path = _DEFAULT_CLIENT_PATH
    token_path = _DEFAULT_TOKEN_PATH

    if not client_path.exists():
        logger.error(
            "OAuth client secrets not found at %s. "
            "Download credentials.json from GCP Console and place it there.",
            client_path,
        )
        raise SystemExit(1)

    try:
        creds = get_credentials(client_path, token_path)
        logger.info("Authorization successful. Token stored at %s", token_path)
        logger.info("Scopes: %s", creds.scopes)
    except OAuthTokenInvalid as exc:
        logger.error("%s", exc)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
