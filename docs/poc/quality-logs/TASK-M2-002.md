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

---

## Independent Validation (test-validator, 2026-04-27)

**Overall verdict: PASS (ACs #1-4)**

### Test Suite Results

Full suite: 452 passed, 1 skipped, 31 warnings — matches implementer's claim.
New tests for this task: 3 — all PASS.

- `tests/llm/test_get_openai_key.py::test_get_openai_key_missing_raises_config_error` — PASS
- `tests/llm/test_get_openai_key.py::test_get_openai_key_present_returns_value` — PASS
- `tests/llm/test_get_openai_key.py::test_get_openai_key_loads_from_dotenv` — PASS

### Per-AC Verdicts

| AC | Verdict | Evidence |
|----|---------|----------|
| AC #1 `.env.example` has `OPENAI_API_KEY` | PASS | Line 8: `OPENAI_API_KEY=sk-...` with comment on line 7 |
| AC #2 `SETUP.md` has "OpenAI API key setup" section | PASS | Subsection at line 85 inside Step 4; covers platform.openai.com, `.env` placement, smoke validation command, and $5-10 hard cap recommendation |
| AC #3 `get_openai_key()` helper correctness | PASS | Runtime-verified: missing key raises `ConfigError` with "OPENAI_API_KEY" and "SETUP.md" in message; present key returns value |
| AC #4 Mocked test for missing-key path | PASS | `test_get_openai_key_missing_raises_config_error` asserts `ConfigError` raised and message contains both "OPENAI_API_KEY" and "SETUP.md" |
| AC #5 Live smoke against real OpenAI | DEFERRED | Requires user's key — not validatable in test environment |

### Dotenv Override Observation

`override=True` is passed to `load_dotenv()` — confirmed by runtime check. When `OPENAI_API_KEY=shell-value` is set in the shell and `OPENAI_API_KEY=dotenv-value` is present in `.env`, the helper returns `dotenv-value` (.env wins). This is non-standard: the conventional default is shell wins. Flagged as an observation — AC #3 does not specify precedence. User may want to revisit if they prefer to set the key via shell export rather than `.env`.

### Smoke Script Structural Test (no key)

```
[smoke] FAILED: OPENAI_API_KEY is not set. Add it to your .env file (see docs/poc/SETUP.md §4 'OpenAI API key setup' for how to obtain one). Get one at https://platform.openai.com/account/api-keys.
exit=1
```

Exit code: 1. Single-line output. Message references both SETUP.md and platform.openai.com. Correct.

### TASKS.md / Quality Log Status

- TASKS.md: ACs #1-4 ticked `[x]`, AC #5 unchecked with "pending user manual verification" note. Status: `In Progress` (correct — AC #5 not yet verified).
- Quality log `docs/poc/quality-logs/TASK-M2-002.md` existed with per-AC verdicts and dry-run smoke output prior to this section.

### Issues by Tier

None.

### Observations

- `override=True` in `load_dotenv()` means `.env` overrides shell-set `OPENAI_API_KEY`. Non-standard but functional. User should be aware if they prefer shell-set keys to take precedence. **Resolved in commit 6929bb0** — override=True removed; shell env now wins per 12-factor convention; regression test test_shell_env_wins_over_dotenv locks the behavior.
- SETUP.md "OpenAI API key setup" is a subsection nested inside Step 4 rather than a top-level section. It is clearly titled and reachable; satisfies AC #2 as worded.

---

## AC #5 — Live Smoke Verification (user-run, 2026-04-27)

User set `OPENAI_API_KEY` in `.env` and ran `.venv/bin/python -m jd_matcher.llm.smoke`.

```
[smoke] OpenAI key OK — model=gpt-4o-mini  echo='OK'  latency=2074ms
exit=0
```

AC #5 PASS. Live cloud round-trip against gpt-4o-mini succeeded; the `get_openai_key()` helper + dotenv loading + OpenAI SDK wiring all function end-to-end. Latency 2.07s is normal for a cold first call; subsequent calls typically sub-second.

**Final task status: 5/5 ACs PASS. TASK-M2-002 closed Done (2026-04-27).**
