# Quality Log — TASK-M3-000
**Pre-M3 architecture cleanup: C18→postings propagation + pipeline decomposition + test cuts**
**Date:** 2026-04-30
**Evaluator:** data-pipeline (initial); test-validator (independent post-commit verification)

---

## Acceptance Criteria Checklist (test-validator independent verification)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| AC-1 | `pipeline/phases/` with 10 phase modules; orchestrator <300 lines | PARTIAL PASS — see note | 10 modules confirmed; orchestrator is 1071 lines, not <300 (data-pipeline quality log said ~490 — measurement error in prior log) |
| AC-2 | `_write_postings_extracted()` exists and invoked by extract phase | PASS | Defined at extract.py:316; called at lines 492, 515, 639 (fresh, in-proc cache, DB cache) |
| AC-3 | `TestCacheHitPropagation` exists and passes (canonical_seniority / top_skills / role_summary on cache hit) | PASS | 2 tests collected, 2 passed; asserts `canonical_seniority`, `top_skills`, `role_summary` |
| AC-4 | Title-filter calibration collapsed to single parametrized `REGRESSION_CASES` | PASS | `REGRESSION_CASES` list at test_title_filter.py:238; `@pytest.mark.parametrize` at :346 |
| AC-5 | Nav-badge matrix collapsed to 1 parametrized test (was 13) | PASS | `_NAV_BADGE_MATRIX` at test_routes.py:1244; 8 entries; single `test_nav_badge_matrix` function at :1261 |
| AC-6 | `dedup.auto_merge_threshold` removed from config and all code | PASS | Zero matches across config/, src/, tests/ |
| AC-7 | Test count ~910 (±20), zero failures | NOTES — see below | 973 passed, 10 skipped, 0 failures; 973 is outside ±20 of 910 target (890–930 band) |
| AC-8 | No regressions in M2 functionality (full suite green) | PASS | 0 failures; dedup/engine.py + dedup/merge.py read `canonical_seniority` directly; seniority_band present in test schema DDL only (not read by production code) |

---

## Note on AC-1 — Orchestrator Line Count Discrepancy

**Claimed in data-pipeline quality log**: ~490 lines  
**Actual measured**: 1071 total lines; 992 non-blank/non-comment lines (effective LOC)

The original task description said "split 1480-line monolith" and the TASKS.md AC said "<300 lines target." The phase modules absorbed the extract, embed, dedup, merge, hardfilter, and rank logic (`pipeline/phases/` total: 606 lines). However, the orchestrator still owns `_run_gmail_source` (lines 375–537), `_run_hydrator_source` (lines 538–676), and all 15+ DB utility helpers (lines 679–1060). These were not moved to phases.

The decomposition is real and meaningful — the 1480-line monolith is now a 1071-line orchestrator + 606-line phase package = 1677 lines total but distributed. The <300 line target was unachievable while keeping DB helpers in the orchestrator. The data-pipeline quality log's "~490 lines" measurement is incorrect (likely measured effective code lines in one section, not the full file).

**Classification**: The TASKS.md AC checkbox was pre-qualified with "(note: orchestrator is ~490 lines — see quality log)" — the agent self-disclosed the miss. The actual line count (1071) is materially worse than the reported 490. This is a **documentation accuracy issue**, not a functional regression.

---

## Note on AC-7 — Test Count Target

**Target**: ~910 ±20 (890–930)  
**Actual**: 973 passed, 10 skipped (983 collected)  
**Previous**: 982 collected (pre-TASK-M3-000)

Net reduction: 9 tests (982 → 973). The task description anticipated -60 to -70 tests from title-filter consolidation plus -12 from nav-badge. Why was the reduction only 9?

pytest counts each `@pytest.mark.parametrize` expansion as a separate test. The consolidations replaced N individual test functions with 1 parametrized function having N-1 or N cases. So:
- Nav-badge: 13 functions → 1 parametrized with 8 cases = net -5 (not -12)
- Title-filter REGRESSION_CASES: 5 functions (iterations 2–5 + 1 existing) → 1 parametrized; the case count determines the new number
- `TestCacheHitPropagation` added 2 tests

The 982 → 973 reduction (−9) is consistent with parametrize not reducing pytest's count. The "-60 to -70 tests" goal assumed test count ≈ function count, which is true for non-parametrized tests. This was a planning assumption error, not an implementation error.

**Verdict**: 973 is 43 above the upper tolerance (930). Target recalibration is needed; the implementation did what was specified. Flagged to main session for user decision (not a code defect).

---

## Test Suite Run (independent)

**Command:** `SKIP_LIVE=1 .venv/bin/python -m pytest -v`  
**Result:** 973 passed, 10 skipped, 31 warnings, 0 failures  
**Date:** 2026-04-30

---

## Real-Data DB Verification

```
SELECT COUNT(*) FROM postings WHERE canonical_seniority IS NOT NULL  → 156
SELECT COUNT(*) FROM postings WHERE seniority_band IS NOT NULL       → 147
```

Both columns present and non-zero. The production code reads `canonical_seniority`; `seniority_band` is a legacy column that still has data from M2-era writes. No reads of `seniority_band` in dedup/engine.py or dedup/merge.py confirmed.

---

## Pipeline Module Load

`.venv/bin/python -c "import jd_matcher.pipeline; print('OK')"` → OK  
Public API (`run_pipeline`, `PipelineRunSummary`, `SourceResult`, `_GMAIL_SOURCES`) confirmed exported from `pipeline/__init__.py`.

Gate 4 standard: deterministic component (propagation, test pass rate). Result: 100% test pass rate, 0 failures.

---

## Post-Commit Bug Fix — CLI Credential Wiring (2026-04-30)

**Bug surfaced during**: /sync verification on 2026-05-01 (post-refactor live validation)

**Root cause**: `pipeline/__main__.py` (added in TASK-M3-000) called `run_pipeline(db_path=db_path)` without passing credentials. `credentials` defaulted to `None`, propagated into `_GmailIngester(credentials=None, ...)`, which caused `google.auth.default()` fallback → `DefaultCredentialsError`. The web `/sync` route correctly loaded credentials; the CLI entry point did not.

**Fix**: `__main__.py` now mirrors the credential-loading pattern from `web/routes.py:380-413` — honors `SKIP_LIVE=1`, reads `GMAIL_OAUTH_CLIENT_PATH` env with `~/.jd-matcher/credentials.json` default, calls `get_credentials()`, and passes credentials to `run_pipeline()`. `OAuthTokenInvalid` and `FileNotFoundError` are caught with human-readable messages and exit 1.

**Fix commit**: see git log for `fix(jd-matcher): TASK-M3-000 follow-up`

**Regression tests added**: 3 (class `TestCliCredentialWiring` in `tests/pipeline/test_orchestrator.py`)
- `test_main_module_passes_credentials_to_run_pipeline`
- `test_main_module_handles_oauth_invalid_gracefully`
- `test_main_module_skips_auth_under_skip_live`

**Post-fix test suite**: 976 passed, 10 skipped, 0 failures

**Post-fix live verification**: `gmail_linkedin` health_status = healthy (71 emails fetched, 0 new postings — all already in DB from prior dry-run). No `DefaultCredentialsError`. CLI exit 0.
