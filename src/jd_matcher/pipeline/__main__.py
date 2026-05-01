import logging
import os
import sys
from pathlib import Path

from jd_matcher.pipeline import run_pipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

db_path = Path(os.environ.get("DB_PATH", Path.home() / ".jd-matcher" / "jd-matcher.db"))

credentials = None
skip_live = os.environ.get("SKIP_LIVE") == "1"
if not skip_live:
    from jd_matcher.auth.gmail_oauth import OAuthTokenInvalid, get_credentials

    client_path = Path(
        os.environ.get(
            "GMAIL_OAUTH_CLIENT_PATH",
            Path.home() / ".jd-matcher" / "credentials.json",
        )
    )
    token_path = Path.home() / ".jd-matcher" / "tokens.json"

    if not client_path.exists():
        print(
            "OAuth client secrets not found. "
            "Run `python -m jd_matcher.auth` to set up credentials first."
        )
        sys.exit(1)

    try:
        credentials = get_credentials(client_path, token_path)
    except OAuthTokenInvalid:
        print(
            "OAuth token is invalid or expired. "
            "Re-authenticate via `python -m jd_matcher.auth`."
        )
        sys.exit(1)
    except FileNotFoundError:
        print(
            "OAuth client secrets file not found. "
            "Re-authenticate via `python -m jd_matcher.auth`."
        )
        sys.exit(1)

summary = run_pipeline(db_path=db_path, credentials=credentials)

print(f"\nPipeline run complete — run_id={summary.run_id}")
print(f"Duration: {(summary.finished_at - summary.started_at).total_seconds():.1f}s")
print(f"Total new postings: {summary.total_new_postings}")
print("\nPer-source results:")
for s in summary.sources:
    status_icon = "OK" if s.health_status == "healthy" else "FAIL"
    print(f"  [{status_icon}] {s.source:<25} {s.health_status}")
    if s.failure_reason:
        print(f"        reason: {s.failure_reason}")
