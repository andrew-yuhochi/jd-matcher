# Quality Log — TASK-M1-001 — Repo bootstrap + project skeleton

**Date**: 2026-04-24
**Agent**: data-pipeline
**Status**: In Progress (blocked on GitHub auth)

---

## TDD C1 Quality Criteria — Results

| Criterion | Result | Notes |
|-----------|--------|-------|
| (a) `git remote -v` shows `andrew-yuhochi/jd-matcher` | BLOCKED | `gh auth login` required — see GitHub section |
| (b) `LICENSE` MIT template with correct year + author | PASS | MIT 2026 Andrew Yu |
| (c) README contains `> Built with [Claude Code](https://claude.ai/code)` directly below top description | PASS | Line 6 of README.md |
| (d) `.gitignore` excludes `.env`, `*.db`, `__pycache__/`, `.venv/`, `.pytest_cache/` | PASS | All patterns present |
| (e) `python -c "import jd_matcher"` succeeds in venv | PASS | Python 3.11.15 venv |
| (f) `pytest -v` runs without import errors (zero tests, zero failures) | PASS | exit code 5 = no tests collected, session started cleanly |
| (g) Repo URL HTTP 200 and visible | BLOCKED | Pending push |

**Overall**: 5/7 criteria PASS. 2 BLOCKED pending `gh auth login`.

---

## Files Created

| File | Description |
|------|-------------|
| `pyproject.toml` | Package config; `jd-matcher`; Python ≥3.11; `src/jd_matcher/` layout |
| `requirements.txt` | Pinned: python-dotenv==1.2.2, pytest==9.0.3, pytest-asyncio==1.3.0 |
| `.gitignore` | Python defaults + `.env`, `*.db`, `.venv/`, `logs/`, `tests/fixtures/real/` |
| `.env.example` | Placeholders: GMAIL_OAUTH_CLIENT_PATH, OPENAI_API_KEY, DB_PATH |
| `LICENSE` | MIT 2026 Andrew Yu |
| `README.md` | Project overview + "Built with Claude Code" badge + Phase badge + Quickstart stub |
| `src/jd_matcher/__init__.py` | Package marker; `__version__ = "0.1.0"` |
| `tests/__init__.py` | Empty marker |
| `tests/fixtures/__init__.py` | Empty marker |
| `tests/conftest.py` | Minimal pytest config (no fixtures yet) |

---

## pip install -e . output (final lines)

```
Successfully built jd-matcher
Installing collected packages: python-dotenv, jd-matcher
Successfully installed jd-matcher-0.1.0 python-dotenv-1.2.2
```

## pytest --collect-only output

```
platform darwin -- Python 3.11.15, pytest-9.0.3, pluggy-1.6.0
rootdir: /Users/andrew.yu/personal/new-structure/projects/jd-matcher
configfile: pyproject.toml
testpaths: tests
collected 0 items
no tests collected in 0.00s
```

(Exit code 5 = no tests collected — correct for a skeleton.)

---

## GitHub Status

**BLOCKED** — `gh auth status` returned: "You are not logged into any GitHub hosts."

Local state:
- Nested git repo initialized at `projects/jd-matcher/.git/` (`git init -b main`)
- All 32 files staged and committed: SHA `1413c97`
- No remote set yet

**User action required**:
```bash
cd projects/jd-matcher
gh auth login          # authenticate to andrew-yuhochi account
gh repo create andrew-yuhochi/jd-matcher --public \
  --description "Local job-posting triage tool — consolidates LinkedIn and Indeed alerts into a single keyboard-driven browser UI with dedup and state tracking." \
  --source=. --remote=origin
git push -u origin main
```

Once pushed, update TASKS.md status to Done and tick the GitHub ACs.

---

## Minor bugs fixed

| # | Bug | Fix |
|---|-----|-----|
| 1 | `setuptools.backends.legacy:build` not available in bundled pip | Changed build-backend to `setuptools.build_meta` |
| 2 | System `python` resolves to pyenv shim with no default set; venv picked up Python 3.9 | Used explicit `/Users/andrew.yu/homebrew/bin/python3.11` for venv creation |
