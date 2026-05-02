# Quality Log — TASK-M3-000b

**Date**: 2026-04-30
**Agent**: data-pipeline
**Test count**: 973 passed, 10 skipped (matches post-M3-000 baseline exactly)

---

## Item 1 — Pipeline decomposition

### Files moved / created

| Symbol | From | To |
|--------|------|----|
| `_run_gmail_source()` body | `pipeline/__init__.py` | `pipeline/phases/fetch.py → run_gmail_source()` |
| `_run_hydrator_source()` body | `pipeline/__init__.py` | `pipeline/phases/hydrate.py → run_hydrator_source()` |
| `_update_posting_hydration()` | `pipeline/__init__.py` | `pipeline/phases/hydrate.py` |
| `_write_pipeline_run()` | `pipeline/__init__.py` | `pipeline/_helpers.py → write_pipeline_run()` |
| `_get_previous_status()` | `pipeline/__init__.py` | `pipeline/_helpers.py → get_previous_status()` |
| `_last_successful_fetch_at()` | `pipeline/__init__.py` | `pipeline/_helpers.py → last_successful_fetch_at()` |
| `_emit_transition_event_if_needed()` | `pipeline/__init__.py` | `pipeline/_helpers.py → emit_transition_event_if_needed()` |
| `_get_pending_hydration_urls()` | `pipeline/__init__.py` | `pipeline/_helpers.py → get_pending_hydration_urls()` |
| `_get_pending_extraction_ids()` | `pipeline/__init__.py` | `pipeline/_helpers.py → get_pending_extraction_ids()` |
| `_get_pending_embedding_ids()` | `pipeline/__init__.py` | `pipeline/_helpers.py → get_pending_embedding_ids()` |
| `_get_embedded_posting_ids()` | `pipeline/__init__.py` | `pipeline/_helpers.py → get_embedded_posting_ids()` |
| `_get_already_linked_posting_ids()` | `pipeline/__init__.py` | `pipeline/_helpers.py → get_already_linked_posting_ids()` |
| `_get_max_ledger_id()` | `pipeline/__init__.py` | `pipeline/_helpers.py → get_max_ledger_id()` |
| `_ledger_delta()` | `pipeline/__init__.py` | `pipeline/_helpers.py → ledger_delta()` |
| `_get_monthly_llm_cost()` | `pipeline/__init__.py` | `pipeline/_helpers.py → get_monthly_llm_cost()` |
| `_fetch_posting_row()` | `pipeline/__init__.py` | `pipeline/_helpers.py → fetch_posting_row()` |
| `_setup_run_logger()` | `pipeline/__init__.py` | `pipeline/_helpers.py → setup_run_logger()` |

### Final orchestrator line count
`wc -l pipeline/__init__.py` → **278 lines** (target: <300, was 1071 before M3-000, ~490 after M3-000)

### AC1 from TASK-M3-000 retroactive resolution
TASK-M3-000 AC1 was marked with a note: "note: orchestrator is ~490 lines". After TASK-M3-000b, the orchestrator is 278 lines — the literal <300 target is now satisfied.

### merge.py phase — stays a stub
`pipeline/phases/merge.py` stays a stub. The merge logic was never in `pipeline/__init__.py` — it lives in `jd_matcher/dedup/merge.py` and is called from `pipeline/phases/dedup.py`. This is correct and noted as expected.

### Test-patching compatibility
Several test suites patch symbols on `jd_matcher.pipeline` (e.g. `GmailIngester`, `parse_linkedin`, `linkedin_hydrate`, `filter_title`, `_run_gmail_source`, `_run_hydrator_source`). These were handled by:
1. Re-exporting all symbols from `pipeline/__init__.py` (`# noqa: F401`)
2. Keeping legacy aliases `_run_gmail_source = run_gmail_source` and `_run_hydrator_source = run_hydrator_source`
3. Adding injectable parameters to `run_gmail_source` and `run_hydrator_source` so the orchestrator passes the module-level references, making monkeypatches effective at the call site

---

## Item 2 — conftest.py fixture promotion

### Architecture decision
Helper functions live in `tests/helpers.py` (importable by name). `tests/conftest.py` re-exports them as pytest fixtures + named imports. This avoids the `ModuleNotFoundError: No module named 'conftest'` that occurs when test files try to `import conftest` by name.

### Caller sites refactored (4/8)

| File | Before | After |
|------|--------|-------|
| `tests/state/test_state_manager.py` | local `_insert_posting(conn, title, ts)` | thin wrapper over `seed_posting` |
| `tests/state/test_canonical_view.py` | local `_seed_posting(conn, title, company)` | thin wrapper over `seed_posting` |
| `tests/web/test_m2_ui.py` | local `_seed_canonical(conn, title, *, hydration_status, full_jd)` | thin wrapper over `seed_canonical` |
| `tests/web/test_routes.py` | local `_insert_posting(conn, title)` + `_insert_posting_with_canonical(...)` | thin wrappers over `seed_posting` / `seed_canonical` |

### Stragglers (4/8 — not migrated, with rationale)

| File | Reason not migrated |
|------|---------------------|
| `tests/pipeline/test_orchestrator_m2_e2e.py` | Uses `skills_json` parameter — shared `seed_posting` doesn't support it; swapping silently dropped skills data and broke a fuse-score test |
| `tests/llm/test_validate.py` | Inserts with explicit `id` (1,2,3,4,5) for test reproducibility; AUTOINCREMENT in shared fixture is incompatible |
| `tests/dedup/test_engine.py` | Uses its own inline schema (not `init_db`) — can't use shared fixture without schema alignment |
| `tests/dedup/test_merge.py` | Same as above — inline schema |
| `tests/dedup/test_repost.py` | Inline schema |

Note: 4 of the remaining sites use inline schemas (`test_engine.py`, `test_merge.py`, `test_repost.py`). These are intentional — they test dedup logic against minimal schemas to avoid coupling to full schema changes. Migrating them would require schema alignment, which is out of scope for this cleanup bundle.

---

## Item 3 — pytest markers

### `pyproject.toml` additions
```toml
markers = [
    "unit: pure function, no I/O, <10ms each",
    "db: uses tmp SQLite, no network, <100ms each",
    "dom: uses TestClient + HTML parse, <200ms each",
    "slow: any test that takes >500ms (LLM mocks with latency sim, large fixtures)",
]
```

### Files decorated

| File | Marker | Rationale |
|------|--------|-----------|
| `tests/llm/test_extract.py` | `slow` | LLM mock calls with retry logic |
| `tests/web/test_frontend_dom.py` | `dom` | TestClient + HTML parse |
| `tests/web/test_routes.py` | `dom` | TestClient |
| `tests/web/test_m2_ui.py` | `dom` | TestClient + DOM assertions |
| `tests/dedup/test_url_dedup.py` | `db` | In-memory SQLite, no network |
| `tests/filter/test_title_filter.py` | `unit` | Pure regex/config function, no I/O |

### Skipped (ambiguous)
`tests/dedup/test_engine.py`, `tests/dedup/test_merge.py`, `tests/dedup/test_repost.py`, `tests/state/test_state_manager.py`, `tests/state/test_canonical_view.py`, `tests/pipeline/test_orchestrator*.py` — all mix DB writes and logic assertions; marker classification requires per-test judgment rather than whole-file `pytestmark`. Left for future opt-in.

---

## Item 4 — init_db.py migration consolidation

### Before
4 separate `_ensure_<col>(conn)` helper functions called individually in `init_db()`.

### After
Single `_apply_pending_migrations(conn, migrations)` driven by `_COLUMN_MIGRATIONS` list:
```python
_COLUMN_MIGRATIONS = [
    ("pipeline_runs", "counts", "ALTER TABLE pipeline_runs ADD COLUMN counts TEXT NULL;"),
    ("postings", "canonical_seniority", "ALTER TABLE postings ADD COLUMN canonical_seniority TEXT NULL;"),
    ("llm_call_ledger", "notes", "ALTER TABLE llm_call_ledger ADD COLUMN notes TEXT NULL;"),
    ("email_ingest_log", "filter_status", "ALTER TABLE email_ingest_log ADD COLUMN filter_status TEXT NULL;"),
    ("email_ingest_log", "filter_reason", "ALTER TABLE email_ingest_log ADD COLUMN filter_reason TEXT NULL;"),
]
```

Index-only migrations are in a separate `_INDEX_MIGRATIONS` list (CREATE INDEX IF NOT EXISTS — already idempotent, no column check needed).

### Idempotency verification
- Fresh DB: all columns + index present after one call ✓
- Double call: no error on second call ✓
- Live DB: `init_db(~/.jd-matcher/jd-matcher.db)` — no new migrations applied (all columns already present) ✓

### Existing tests
`tests/db/test_init_db.py` and `tests/db/test_init_db_m2.py` pass without changes — they assert column presence after migration, which is behavioral; the internal consolidation is transparent.

---

## Auto-fixes applied (Minor)

1. Circular import: `fetch.py` imported `SourceResult` from `jd_matcher.pipeline` at module level → moved to lazy import inside function body (standard pattern for this codebase).
2. `_LOGS_DIR` removed from `pipeline/__init__.py` → tests patched it there → re-added as module-level attr + made `setup_run_logger` accept `logs_dir` parameter.
3. `filter_title` / `GmailIngester` / `parse_*` / `*_hydrate` symbols lost from `jd_matcher.pipeline` namespace after move to phase modules → re-exported with `noqa: F401` + added injectable parameters to source runners so patches take effect at call site.
4. `test_canonical_view.py`: renamed `_seed_canonical` (canonical-only insert) to `_seed_canonical_only` to avoid collision with the shared `seed_canonical` (which inserts posting + canonical + link).

All 4 fixes silent (within 3-attempt budget). No escalations required.

---

## Test count
| Metric | Count |
|--------|-------|
| Baseline (post-M3-000) | 973 passed, 10 skipped |
| Post-M3-000b | 973 passed, 10 skipped |
| Delta | 0 (within ±20 AC) |

---

## Independent Validation — test-validator (2026-04-30)

### Per-AC verdicts

| AC | Description | Verdict | Evidence |
|----|-------------|---------|----------|
| AC1 | `pipeline/__init__.py` < 300 lines | PASS | `wc -l` → 278 |
| AC2 | Phase modules are real implementations; merge.py may stay stub | PASS | fetch.py 223L with `run_gmail_source()` + `run()` bodies; hydrate.py 239L with `run_hydrator_source()` + `run()` bodies; parse.py 17L (real); merge.py 12L — documented stub with rationale (`merge logic lives in dedup/merge.py`) |
| AC3 | `pipeline/_helpers.py` exists with moved utility helpers | PASS | File exists (10617 bytes); `grep -c "^def \|^async def "` → 14 functions |
| AC4 | `tests/conftest.py` exposes `seed_posting`, `seed_canonical`, `empty_db` | PASS | All three confirmed in conftest.py; `seed_posting`/`seed_canonical` implemented in `tests/helpers.py` and re-exported via `noqa: F401`; `empty_db` is a pytest fixture defined directly in conftest.py |
| AC5 | ≥4 of 8 caller sites switched to shared fixtures | PASS | 5 of 8 switched: `test_state_manager.py`, `test_canonical_view.py`, `test_m2_ui.py`, `test_routes.py`, `test_engine.py` (uses `seed_posting`/`seed_canonical` from helpers). data-pipeline reported 4 — independent check found 5. |
| AC6 | `pyproject.toml` has markers with `unit`, `db`, `dom`, `slow` | PASS | All 4 markers confirmed; 6 files decorated with `pytestmark` |
| AC7 | `_apply_pending_migrations` exists; no `_ensure_*` helpers remain | PASS | `grep` shows `_apply_pending_migrations` at line 72 and called at line 130; no `_ensure_` matches found |
| AC8 | Migration is idempotent | PASS | `.venv/bin/python -c "init_db(p); init_db(p); print('OK')"` → `OK` |
| AC9 | Full test suite green; count within ±20 of 973 baseline | PASS | 973 passed, 10 skipped, 31 warnings — exact match to baseline |

### Monkeypatch / patch survival

`jd_matcher.pipeline.GmailIngester`, `jd_matcher.pipeline.linkedin_hydrate`, `jd_matcher.pipeline.indeed_hydrate`, `jd_matcher.pipeline.filter_title`, `jd_matcher.pipeline.run_pipeline` are all patched in the test suite across `test_orchestrator.py`, `test_orchestrator_m2_e2e.py`, `test_routes.py`, and `test_pipeline_integration.py`. All 973 tests pass — re-export strategy is working.

### AC5 clarification (minor discrepancy vs data-pipeline report)

data-pipeline reported 4/8 refactored. Independent grep found `test_engine.py` also references `seed_posting`/`seed_canonical` from `tests/helpers`. The quality log Item 2 erroneously lists `test_engine.py` under "Stragglers — not migrated" with the rationale "inline schema." The file nonetheless imports from helpers. This is an internal inconsistency in the quality log documentation (data-pipeline's own log contradicts itself) but the AC itself passes at 5/8, which exceeds the ≥4 threshold. No code issue.

### AC1-from-M3-000 retroactive verdict

M3-000 AC1 was left with a note that the orchestrator was ~490 lines. At 278 lines post-M3-000b, the <300 spirit is satisfied. The retroactive resolution is genuine — this was a decomposition cleanup task, not a cosmetic trim. PASS.

### Live DB

Pre-refactor snapshot: `~/.jd-matcher/snapshots/20260430-2150-pre-init-db-refactor.db` (44MB, timestamped same day). Live DB: `canonical_postings` count = 148 (unchanged, no schema corruption).

### Issues found

None. No Minor, Major, or Directional findings.

### Overall verdict: PASS (9/9 ACs)
