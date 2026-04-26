"""
Entry point: python -m jd_matcher.web

Reads JD_MATCHER_PORT (default 8765) and JD_MATCHER_HOST (default 127.0.0.1).
0.0.0.0 is rejected — this tool is local-only (TDD §1.4).
"""

from __future__ import annotations

import os
import sys


def main() -> None:
    host = os.environ.get("JD_MATCHER_HOST", "127.0.0.1")
    if host == "0.0.0.0":
        print(
            "ERROR: binding to 0.0.0.0 is not permitted — "
            "jd-matcher is a local-only tool (TDD §1.4). "
            "Set JD_MATCHER_HOST to 127.0.0.1 or omit the variable.",
            file=sys.stderr,
        )
        raise ValueError(
            "JD_MATCHER_HOST=0.0.0.0 is rejected; use 127.0.0.1"
        )

    port_str = os.environ.get("JD_MATCHER_PORT", "8765")
    try:
        port = int(port_str)
    except ValueError:
        print(f"ERROR: invalid JD_MATCHER_PORT={port_str!r}", file=sys.stderr)
        sys.exit(1)

    import uvicorn

    from jd_matcher.web.app import app

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
