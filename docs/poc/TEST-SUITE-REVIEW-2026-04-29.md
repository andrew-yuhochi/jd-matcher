# Test Suite Review — jd-matcher PoC — 2026-04-29

**Trigger**: User directive at M2 close (BACKLOG 68440bc) — review test suite before drafting M3 tasks. 992 tests collected at M2 close is high for PoC scope.
**Scope**: Test suite only (production code architecture in ARCHITECTURE-REVIEW-2026-04-29.md).

---

## Executive summary

The test suite is functionally sound — all 992 tests collect cleanly under the correct `.venv` (Python 3.11), the suite gates real regressions (M2-010 column mismatch, M2-012 Jobright propagation), and the parametrize marker is used in the right places. The count inflated for three distinct reasons: (1) nav-badge tests were written one permutation per test function rather than as a parametrized matrix; (2) the title-filter file accumulated five successive calibration blocks that are now redundant — the earlier iterations are subsumed by later ones; and (3) fixture-seeding helpers (`_insert_posting`, `_seed_canonical`, etc.) were re-implemented 8+ times across files instead of being promoted to `conftest.py`. There is also one meaningful coverage gap: the extraction-cache cache-hit path is tested for ledger writes but not for whether the extraction fields (`seniority_band`, `top_skills`, `role_summary`) are actually propagated to the `postings` table on a cache hit — exactly the class of bug that bit the Jobright canonicals in M2-012.

One Minor environment issue discovered: the `conftest.py` at the root is a 4-line placeholder; the project's correct venv is `.venv/` (not `venv/`), and the memory file for this agent had the wrong path. This could mislead future sub-agents. The CLAUDE.md is already correct, so the risk is low.

---

## 1. Test inventory

| File | LOC | Tests | Surface |
|---|---|---|---|
| `filter/test_title_filter.py` | 460 | 158 | Title deny/allow filter |
| `web/test_routes.py` | 1550 | 60 | HTTP routes / nav badges |
| `dedup/test_engine.py` | 1503 | 56 | Two-stage dedup (FUSE math + scenarios) |
| `web/test_m2_ui.py` | 1416 | 51 | DOM card rendering (M2 UI) |
| `dedup/test_merge.py` | 784 | ~35 | Merge / apply-decision |
| `test_pipeline_log_integration.py` | 744 | ~30 | Pipeline log integration |
| `llm/test_extract.py` | 739 | ~28 | LLM extraction + cache |
| `pipeline/test_orchestrator.py` | 560 | ~25 | Orchestrator step sequencing |
| `state/test_canonical_view.py` | 474 | 22 | Canonical card view (select_main) |
| `llm/test_embed.py` | 474 | 26 | Embedding + cache |
| `ingest/test_gmail.py` | 468 | ~60 (parametrized) | Gmail ingest fixtures |
| `dedup/test_calibrate.py` | 464 | 28 | Calibration report + metrics |
| `pipeline/test_orchestrator_m2_e2e.py` | 462 | ~20 | M2 end-to-end |
| `filter/test_title_filter.py` _(calibration blocks)_ | — | 90 of 158 | Filter calibration iterations 2-7 |
| `web/test_keyboard_handler.py` | 439 | 36 | JS keyboard handler (source scan) |
| `dedup/test_classifier.py` | 428 | ~30 | LLM gatekeeper classifier |
| `state/test_state_manager.py` | 502 | 20 | State manager CRUD |
| `hydrate/test_indeed_hydrator.py` | 507 | 22 | Indeed hydrator |
| `hydrate/test_linkedin_hydrator.py` | 360 | 32 | LinkedIn hydrator |
| `web/test_frontend_dom.py` | 507 | 17 | Frontend DOM (card structure) |
| `parse/test_linkedin_email.py` | 283 | 41 | LinkedIn email parser |
| `filter/test_validate.py` | 203 | 7 | Filter validation |
| `parse/test_indeed_email.py` | 189 | 21 | Indeed email parser |
| `parse/test_indeed_pagead.py` | 443 | 14 | Indeed page-ad parser |
| `test_report_cli.py` | 389 | ~18 | Report CLI |
| `llm/test_validate.py` | 384 | ~20 | LLM validate / cache-bust |
| `scripts/test_analyze_top_skills.py` | 200 | ~8 | Top-skills analysis script |
| `dedup/test_repost.py` | 319 | ~12 | Repost detection |
| `dedup/test_url_dedup.py` | 270 | 11 | URL dedup |
| `web/test_events_endpoint.py` | 256 | 19 | Events endpoint |
| `hydrate/test_browser_fetcher.py` | 257 | 13 | Browser fetcher |
| `db/test_init_db.py` | 292 | 9 | Schema init (M1 baseline) |
| `db/test_init_db_m2.py` | 236 | 6 | Schema init (M2 tables) |
| `ingest/test_gmail_log_writer.py` | 171 | ~8 | Gmail log writer |
| `llm/test_canonical_skills_regression.py` | 155 | ~4 | Canonical skills regression |
| `db/test_email_ingest_log_schema.py` | 155 | ~5 | Email ingest log schema |
| _(llm/providers, auth, hydrate/rate_limiter, parse/email_log)_ | ~600 | ~50 | Supporting components |
| **Total** | **~18,600** | **992** | |

---

## 2. Outdated / orphan tests

**No true orphans found** — the suite passes cleanly. However, two categories of stale-intent tests exist:

**2a. Superseded calibration blocks in `tests/filter/test_title_filter.py`**

Lines 234–459 contain five `test_iteration_N_calibration` parametrized blocks (iterations 2, 3, 4, 5, 7). Each block was written when a new filter iteration shipped, locking in the expected behavior at that point. By M2 close, the production filter already encapsulates all of these constraints: every case in iterations 2, 3, 4, and 5 is a logical subset of the current filter config. Iteration 4 comments even acknowledge this ("Iteration 4: Director carve-outs removed — these now DROP", overriding cases from Iteration 2). Running all five blocks adds ~90 test executions but provides no marginal coverage beyond the primary `DENY_CASES`/`PASS_CASES` parametrize blocks.

Recommended removal: collapse iterations 2–7 into a single `test_calibration_regression` parametrized block containing only cases that represent non-obvious allow/deny decisions (ambiguous titles, company-qualified drops). Estimated reduction: ~70 tests, ~130 LOC.

**2b. Nav-badge test verbosity in `tests/web/test_routes.py`** (lines 1244–1540)

13 separate test functions cover the same 3-tab × 3-page badge matrix. The functions share near-identical setup (insert N postings, apply/dismiss, assert badge value). This is not an orphan problem but a consolidation opportunity — see Section 7.

**2c. `import re` inside test bodies**

`tests/web/test_routes.py` has 13 inline `import re` statements inside individual test functions. These are not wrong but are a code-smell indicator of copy-paste expansion. Moving `import re` to the module level is a one-line fix.

---

## 3. Fixture duplication

The following `_insert_posting` / `_seed_canonical` helpers exist as module-level private functions, not shared fixtures:

| Helper | File | Approximate LOC |
|---|---|---|
| `_insert_posting` | `tests/web/test_routes.py:126` | 12 |
| `_insert_posting_with_canonical` | `tests/web/test_routes.py:140` | 28 |
| `_insert_posting_with_jd` | `tests/web/test_routes.py:721` | 12 |
| `_seed_canonical` | `tests/web/test_m2_ui.py:34` | 38 |
| `_seed_canonical_enriched` | `tests/web/test_m2_ui.py:682` | 50+ |
| `_seed_canonical` | `tests/state/test_canonical_view.py:75` | ~35 |
| `_insert_posting` | `tests/state/test_state_manager.py:45` | 12 |
| `_insert_posting` | `tests/dedup/test_engine.py:141` | ~25 |
| `_insert_posting` | `tests/dedup/test_repost.py:102` | 12 |
| `_insert_posting` | `tests/dedup/test_merge.py:155` | ~25 |
| `_seed_db` | `tests/filter/test_validate.py:32` | ~20 |
| `_insert_posting` | `tests/llm/test_validate.py:79` | ~15 |

Additionally, 16 raw `INSERT INTO posting_canonical_links` strings appear inline across web and state test files (counted directly).

The root conftest (`tests/conftest.py`) is a 4-line placeholder. No shared DB-seeding fixtures exist. Extracting the three most-used patterns into `tests/conftest.py` shared fixtures would reduce duplication: (a) a `seed_posting` fixture returning `(posting_id, conn)`, (b) a `seed_canonical` fixture returning `(posting_id, canonical_id, conn)`, (c) an `empty_db` fixture wrapping `init_db(tmp_path / "test.db")`. Estimated reduction: ~150–200 LOC, and future M3 DOM tests would not re-invent these patterns.

**Jaccard function duplication**: `tests/dedup/test_calibrate.py` (class `TestJaccardScore`) and `tests/dedup/test_engine.py` (class `TestJaccard`) both test a `_jaccard_score` function, but they import from different modules (`calibrate` vs `engine`). If both modules have their own implementation of Jaccard, these tests are correct as written. If one delegates to the other, one set of tests is redundant. Worth verifying before M3 — this is a potential 12-test reduction.

---

## 4. Test categorization

**Current state**: Only two marker types are in active use:

- `@pytest.mark.parametrize` — 24 usages across 12 files (correct, good)
- `@pytest.mark.skipif(SKIP_LIVE, ...)` — 8 usages guarding live API calls

No speed-tier markers exist (`slow`, `fast`, `integration`, `requires_llm`). The full suite takes approximately 3–5 seconds under `SKIP_LIVE=1` based on collection time; runtime is fast. However, the M3 smart layer (LLM extraction, fit scoring) will introduce tests that are genuinely slow. Without markers, the developer will have no way to run a tight inner loop.

**Recommended marker scheme for M3 onward**:

```
@pytest.mark.unit       # pure function, no I/O, <10ms each
@pytest.mark.db         # uses tmp SQLite, no network, <100ms each
@pytest.mark.dom        # uses TestClient + HTML parse, <200ms each
@pytest.mark.slow       # any test that takes >500ms (LLM mocks with latency sim, large fixtures)
```

Add `[markers]` section to `pyproject.toml`. Default CI run: `pytest -m "not slow"`. Full run: `pytest` (current behavior unchanged). This is a one-day M3 setup task with no test rewrites — just decorating existing files and adding `pyproject.toml` entries.

---

## 5. Mocking patterns

**Consistent patterns (good)**:
- LLM provider mocking is consistent: `MagicMock()` with `.extract.return_value` / `.embed.return_value` set from a `_make_provider()` factory. This pattern appears in `test_extract.py`, `test_classifier.py`, `test_calibrate.py`, and `test_orchestrator_m2_e2e.py` and follows the same interface.
- `SKIP_LIVE` env-var gating is used consistently for all live tests.

**Inconsistencies**:

- `tests/web/test_keyboard_handler.py` reads the real `app.js` file from `src/jd_matcher/web/static/app.js` via filesystem access — it is a static-file source-scan rather than a behavior test. This is a reasonable technique for a JS file that cannot be unit-tested via Python, but the file-path coupling is fragile: if the static file moves, 36 tests fail at collection time. No mock is needed, but the path should come from a `conftest.py` fixture (`@pytest.fixture(scope="module")`) rather than a module-level `_js_source()` function that opens the file on every call.

- `tests/web/test_routes.py` and `tests/web/test_m2_ui.py` both create `TestClient(app)` but use different DB injection patterns. `test_routes.py` uses a monkeypatch on the app's DB path setting; `test_m2_ui.py` uses a `db` fixture and a `client` fixture that references it. Neither approach is wrong, but they are different, making it hard to share setup code between the two files.

- No tests mock too aggressively: the system under test is always the production function, with only external boundaries (LLM providers, file I/O) mocked. This is correct.

---

## 6. Coverage gaps

**Gap 1 — extraction-cache cache-hit propagation (M2-012 class of bug)**

The Jobright propagation gap (commit `962cf05`) was a direct `UPDATE` from cache that had not been reached by tests. The current cache-hit test (`test_ledger_row_written_on_cache_hit`, `test_extract.py:489`) only asserts that the ledger row was written with `status='cache_hit'`. It does NOT assert that `postings.seniority_band`, `postings.top_skills`, and `postings.role_summary` are updated when a cache hit occurs. If the `UPDATE` path is ever accidentally removed or conditional, the test will still pass.

**Recommended test**: a new `TestCacheHitPropagation` class in `test_extract.py` that: (a) inserts a posting with empty `seniority_band`/`top_skills`, (b) pre-seeds the `extraction_cache`, (c) calls `extract_canonical`, and (d) asserts the posting fields were populated from cache. This is the same class of guard as `test_canonical_seniority_populated_from_posting_seniority_band` in `test_merge.py`.

**Gap 2 — Schema column name contract across layers**

The M2-010 column mismatch (`postings.canonical_seniority` vs `seniority_band`) was caught late because no test asserted "the column that `extract_canonical` writes to is the same column that `_fetch_posting` reads from." The regression test added in `test_merge.py:734` guards this now, but only for the merge layer. There is no equivalent guard for the web layer: `test_routes.py` and `test_m2_ui.py` both seed `canonical_postings.canonical_seniority` directly in test fixtures, bypassing the extraction → posting → merge chain. If the column were renamed again, the web tests would still pass against stale seed data.

**Recommended test**: an integration fixture in `conftest.py` that runs the full extraction → merge path on a minimal posting, then checks the rendered card DOM contains the expected seniority value. This does not need to be a new test file — it can be one parametrized case added to `test_orchestrator_m2_e2e.py`.

---

## 7. Specific consolidation targets

**Target A — Nav-badge matrix in `tests/web/test_routes.py` (HIGH)**

Lines 1244–1540: 13 test functions covering (3 pages × badge presence) + (badge values at N applied/dismissed). The setup is identical across functions — insert N postings, apply/dismiss some, fetch a page, assert regex. This is a textbook parametrize candidate:

```python
@pytest.mark.parametrize("page,n_applied,n_dismissed,expected_applied,expected_dismissed", [
    ("/",         0, 0, 0, 0),
    ("/",         4, 0, 4, 0),
    ("/",         0, 5, 0, 5),
    ("/applied",  3, 0, 3, 0),
    ("/applied",  0, 0, 0, 0),
    ("/dismissed",0, 2, 0, 2),
    ("/dismissed",0, 0, 0, 0),
])
def test_nav_badge_matrix(page, n_applied, n_dismissed, expected_applied, expected_dismissed, client, seeded_db):
    ...
```

Estimated reduction: 13 functions → 1 parametrized test (7 cases). **-12 tests, -250 LOC**.

**Target B — Title filter calibration iterations in `tests/filter/test_title_filter.py` (HIGH)**

Lines 234–459 contain five `test_iteration_N_calibration` blocks totaling approximately 90 test cases. The non-obvious, non-redundant cases (ambiguous titles that needed a rule change, company-qualified drops, staffing-firm guards) should be extracted into a single `REGRESSION_CASES` list and tested in one parametrized function. Obvious deny/pass cases that are already represented in `DENY_CASES`/`PASS_CASES` should be removed.

Estimated reduction: **-60 to -70 tests, -130 LOC** after deduplication.

**Target C — Keyboard handler key-presence tests in `tests/web/test_keyboard_handler.py` (MED)**

Lines 107–151: 8 individual `test_app_js_handles_X_key()` functions, each reading the same file and asserting a string is present. These should be one parametrized test:

```python
@pytest.mark.parametrize("key", ["j", "k", "e", "d", "a", "o", "?", "Escape"])
def test_app_js_handles_key(key: str, js_source: str) -> None:
    assert f'"{key}"' in js_source or f"'{key}'" in js_source
```

Estimated reduction: 8 → 1 parametrized (8 cases). **-7 tests, -40 LOC**.

**Target D — Event-type parametrize expansion in `tests/web/test_keyboard_handler.py`** (lines 154–169, MED)

4 individual functions asserting event string presence (`session_start`, `card_dismissed`, `card_marked_applied`, `tab_switched`) are a single parametrize candidate. **-3 tests, -20 LOC**.

**Target E — `_insert_posting` → `conftest.py` fixture promotion (MED)**

The 8 independent `_insert_posting` helper implementations could be replaced by a single `pytest.fixture` or a shared helper module at `tests/helpers.py`. **0 test-count delta, -150 LOC across the suite**.

---

## Prioritized recommendations

| Priority | Action | Estimated impact | Why now |
|---|---|---|---|
| HIGH | Collapse `test_iteration_N_calibration` blocks (iterations 2–7) into one `REGRESSION_CASES` parametrized block; remove cases already covered by `DENY_CASES`/`PASS_CASES` | -60 to -70 tests, -130 LOC | Before M3 adds more iteration blocks; filter is now stable |
| HIGH | Parametrize nav-badge matrix (13 functions → 1 with 7-case parametrize) in `test_routes.py` | -12 tests, -250 LOC | Badge logic is frozen; this is pure test debt |
| HIGH | Add `TestCacheHitPropagation` in `test_extract.py` — assert extraction fields written to `postings` on cache hit | +1 test, +40 LOC | Covers the exact class of bug (M2-012 Jobright) that tests missed |
| MED | Parametrize keyboard key-presence tests (8 → 1 parametrized) | -7 tests, -40 LOC | Small win; pairs with HIGH above to clear keyboard_handler tech debt |
| MED | Promote `_insert_posting` + `_seed_canonical` to `tests/conftest.py` shared fixtures | 0 test delta, -150 LOC | Required before M3 DOM tests are written, or the pattern repeats |
| MED | Add `[markers]` section to `pyproject.toml` with `unit`, `db`, `dom`, `slow` | 0 test delta, 0 LOC delta | M3 LLM tests will be slow; without markers, developer has no fast inner loop |
| LOW | Move `import re` to module level in `test_routes.py` (13 occurrences) | 0 test delta, -13 LOC | Trivial cleanup; catches copy-paste pattern |
| LOW | Verify whether `calibrate._jaccard_score` and `engine._jaccard_score` are the same function; if so, remove `TestJaccardScore` from `test_calibrate.py` | -6 tests, -20 LOC | Low risk, small reward |
| LOW | Add integration guard test asserting seniority flows extraction → posting → merge → DOM | +1 test, +40 LOC | Low urgency — M2-010 regression test in test_merge.py covers the worst case |

---

## Recommended action for M3 planning

**Pre-M3 cleanup task (one-shot, ~0.5 day estimated)**:
Treat HIGH items as a single cleanup task before M3 kicks off: (1) collapse title-filter calibration blocks, (2) parametrize nav-badge matrix, (3) add cache-hit propagation test, (4) move `_insert_posting` helpers to `tests/conftest.py`. This is purely mechanical refactoring — no logic change. Output: test count drops from 992 to approximately 910, LOC drops by ~400.

**Patterns to enforce going forward in M3**:
- All new DOM tests MUST use the shared `seed_canonical` conftest fixture — no inline `INSERT INTO posting_canonical_links` in M3 test files.
- All new M3 components that touch LLM calls get a `requires_llm` marker; all tests using `TestClient` get a `dom` marker. Marker scheme must be in `pyproject.toml` before the first M3 task ships.
- New calibration cases (fit_score, role_orientation thresholds) go into one parametrized regression block per component — not one function per case.

**Items to defer**:
- Keyboard handler event-type parametrize (4 functions → 1) — low ROI, defer to natural cleanup.
- Jaccard function audit (calibrate vs engine) — defer until the architect decides whether `calibrate.py` re-exports from `engine.py` or re-implements. The answer affects whether to keep both test classes.
- Integration guard for seniority end-to-end flow — defer to M3 when the smart layer touches these fields again and the guard becomes directly relevant.
