"""Smoke test: verifies the OpenAI key works by sending a 1-token completion.

Run as:
    .venv/bin/python -m jd_matcher.llm.smoke

Exit 0 on success, exit 1 on any failure.
"""
import sys
import time

import openai

from jd_matcher.errors import ConfigError
from jd_matcher.llm import get_openai_key

_MODEL = "gpt-4o-mini"
_OPENAI_KEYS_URL = "https://platform.openai.com/account/api-keys"


def main() -> None:
    try:
        key = get_openai_key()
    except ConfigError as exc:
        print(
            f"[smoke] FAILED: {exc} Get one at {_OPENAI_KEYS_URL}.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = openai.OpenAI(api_key=key)
    start = time.monotonic()
    try:
        response = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": "respond with OK"},
                {"role": "user", "content": "ping"},
            ],
            max_tokens=1,
        )
    except openai.AuthenticationError as exc:
        print(
            f"[smoke] FAILED: API key rejected (401). Check OPENAI_API_KEY in .env. Detail: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except openai.OpenAIError as exc:
        print(
            f"[smoke] FAILED: OpenAI API error — {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:  # network errors, etc.
        print(
            f"[smoke] FAILED: Unexpected error — {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    latency_ms = int((time.monotonic() - start) * 1000)
    echo = (response.choices[0].message.content or "").strip()
    print(f"[smoke] OpenAI key OK — model={_MODEL}  echo='{echo}'  latency={latency_ms}ms")


if __name__ == "__main__":
    main()
