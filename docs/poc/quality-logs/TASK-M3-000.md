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

---

## Post-Commit Bug Fix — Orchestrator Silent Death After Gmail Phase (2026-04-30)

**Bug surfaced during**: live sync run `be8e8ae2` on 2026-05-01 (07:41 UTC) — 121 new LinkedIn postings ingested, 0 downstream phases ran.

**Root cause (Major-tier, Gate 5 diagnosed before fix):**

With 64 pending-hydration URLs and no `SKIP_LIVE`, the hydrator calls `_fetch_live()` → `HYDRATOR_RATE_LIMITER.wait()` → `time.sleep(30)` for each URL. Total sleep time: 64 × 30s = 32 minutes. The user killed the process (SIGTERM/Ctrl+C → `KeyboardInterrupt`) while it was blocked in `time.sleep()`. `KeyboardInterrupt` is `BaseException` (not `Exception`), so it bypassed:
- The per-URL `except Exception` handler in `run_hydrator_source`
- The outer `except Exception` handler in `run_hydrator_source`
- The `run_pipeline` function (no handler at all)

Process died after the `source_complete` log for gmail — no `pipeline_runs` rows written for hydrator, extract, embed, dedup, hardfilter, or rank. JSONL log was only 3 lines / 528 bytes. C11 mandatory-persistence invariant violated for 6 sources.

**Why this wasn't caught by previous tests**: The pre-fix test runs `f8cc3e3f` (07:47) and `a0429a90` (07:52) that the earlier data-pipeline agent used for verification both had `new_postings=0` (dedup'd), so `get_pending_hydration_urls` returned 0 URLs and the hydrator completed immediately. The bug only manifests when there are ≥1 pending hydration URLs in a live run.

**Pre-refactor behavior**: The 1480-line monolith had the same BaseException gap (no `except BaseException` in the URL loop), but before M3-000 the DB had fewer accumulated partial postings so the rate-limiter sleep was short (1-2 URLs) and users didn't kill the process.

**Fix (commit: see below):**

1. **`pipeline/__init__.py`** — wrapped the hydrator loop in `except (KeyboardInterrupt, SystemExit)` to defer the signal; wrapped each downstream phase (extract, embed, dedup, hardfilter, rank) in `except BaseException` that writes a `failed` pipeline_runs row and continues to the next phase; added `_deferred_interrupt` re-raise at the end of `run_pipeline` after `pipeline_complete` is logged.

2. **`pipeline/phases/hydrate.py`** — added `except (KeyboardInterrupt, SystemExit)` handler in the URL loop; calls `_flush_partial_hydrator_result()` (new helper) to write the hydrator's pipeline_runs row before re-raising, ensuring C11 is satisfied even when the process is interrupted mid-URL.

**Regression tests added** (3 tests in `TestOrchestratorContinuesPastHydratorFailure`):
- `test_regular_exception_from_hydrator_does_not_skip_downstream_phases` — hydrator raises `RuntimeError`, verifies all 7 downstream pipeline_runs rows written
- `test_keyboard_interrupt_from_hydrator_persists_all_phase_rows` — hydrator raises `KeyboardInterrupt`, verifies extract/embed/dedup/hardfilter/rank rows written before re-raise
- `test_pipeline_complete_event_written_after_hydrator_failure` — verifies `pipeline_complete` appears in JSONL log after hydrator crash

**Post-fix test suite**: 979 passed, 10 skipped, 0 failures

**Directional flag**: The 30s/URL rate limit (TDD §C5) is correct for normal volume but impractical for catch-up runs of 64+ URLs (32 min blocking). Adding a configurable `max_hydration_per_run` cap (e.g. 20 URLs per sync) is logged as a backlog item — implementing it requires a TDD §C5 amendment. Not fixed here (out of scope for this bug fix).
