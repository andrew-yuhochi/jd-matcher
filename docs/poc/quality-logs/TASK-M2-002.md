# Quality Log — TASK-M2-002
# OpenAI API key setup + .env + SETUP.md

Date: 2026-04-27
Agent: data-pipeline

---

## AC Verdicts

| AC | Description | Verdict |
|----|-------------|---------|
| AC #1 | `.env.example` contains `OPENAI_API_KEY` entry with placeholder | PASS |
| AC #2 | `SETUP.md` has section "OpenAI API key setup" with platform.openai.com walkthrough | PASS |
| AC #3 | `get_openai_key()` raises `ConfigError` with message referencing OPENAI_API_KEY + SETUP.md | PASS |
| AC #4 | Mocked tests: missing env var raises `ConfigError` with actionable message | PASS |
| AC #5 | Smoke script works end-to-end against real OpenAI (live test) | PENDING — user action required |

---

## Pytest Summary

```
452 passed, 1 skipped, 31 warnings in 6.22s
```

Previous baseline: 449 passed, 1 skipped.
New tests added: 3 (`tests/llm/test_get_openai_key.py`).
No regressions.

### New test names
- `tests/llm/test_get_openai_key.py::test_get_openai_key_missing_raises_config_error`
- `tests/llm/test_get_openai_key.py::test_get_openai_key_present_returns_value`
- `tests/llm/test_get_openai_key.py::test_get_openai_key_loads_from_dotenv`

---

## Smoke Script — Dry-Run Error Path Output

Verified by running `.venv/bin/python -m jd_matcher.llm.smoke` with `OPENAI_API_KEY` unset and no `.env` in cwd.

```
[smoke] FAILED: OPENAI_API_KEY is not set. Add it to your .env file (see docs/poc/SETUP.md §4 'OpenAI API key setup' for how to obtain one). Get one at https://platform.openai.com/account/api-keys.
Exit code: 1
```

Error path works correctly — exits non-zero with an actionable message pointing to SETUP.md and the OpenAI key management URL.

---

## Files Created / Modified

| File | Action |
|------|--------|
| `src/jd_matcher/errors.py` | Created — `ConfigError` exception class |
| `src/jd_matcher/llm/__init__.py` | Created — `get_openai_key()` helper |
| `src/jd_matcher/llm/smoke.py` | Created — 1-token completion smoke test script |
| `tests/llm/__init__.py` | Created — package init |
| `tests/llm/test_get_openai_key.py` | Created — 3 mocked unit tests |
| `.env.example` | Pre-existing — `OPENAI_API_KEY=sk-...` entry already present from scaffold |
| `requirements.txt` | Modified — added `openai==2.32.0` |
| `docs/poc/SETUP.md` | Pre-existing — content-writer added "OpenAI API key setup" subsection (lines 85–103) |
| `docs/poc/TASKS.md` | Modified — ACs #1–4 ticked; AC #5 marked pending |

---

## Minor Bug Fixed (self-corrected, attempt 1 of 3)

`load_dotenv()` without an explicit path uses its own search logic and does not honour `monkeypatch.chdir()` in tests. Fixed by passing `dotenv_path=Path.cwd() / ".env"` so the helper reads from the process's current working directory at call time. This also makes the production behaviour correct: the script loads `.env` from wherever it is invoked.

---

## AC #5 — Pending User Action

AC #5 will be verified by the user after setting `OPENAI_API_KEY` in `.env`:

1. Copy `.env.example` to `.env` (if not done): `cp .env.example .env`
2. Set the key in `.env`: `OPENAI_API_KEY=sk-<your-key>`
3. Run: `.venv/bin/python -m jd_matcher.llm.smoke`
4. Expected output: `[smoke] OpenAI key OK — model=gpt-4o-mini  echo='...'  latency=Xms`

On user confirmation, a follow-up commit will tick AC #5 [x] and mark TASK-M2-002 Done.
