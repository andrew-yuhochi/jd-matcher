# Quality Log — TASK-M2-010
## Pipeline Orchestrator + State Manager Extension (C11 + C22)
**Date**: 2026-04-29
**Agent**: data-pipeline

---

## Scope

- C11 pipeline orchestrator: wired C19 filter → URL-dedup → hydrate → C18 LLM-extract → C20 embed → C21 content-dedup → C29 merge → C30 repost → C2 store
- C22 canonical_view read-side state manager: `select_main()`, `is_canonical_applied()`, `is_canonical_dismissed()`, `get_canonical_state()`
- Two new `pipeline_runs` rows per run: `llm_extraction` and `embedding`
- Cost-watchdog at run-end
- Schema migration: `pipeline_runs.counts` column, `postings.canonical_seniority` column (live DB compat fix)

---

## Methodology

- **Deterministic tests**: 21 C22 unit tests, 25 orchestrator tests (18 existing + 7 new M2-E2E tests)
- **Demo artifact**: live `python -m jd_matcher.pipeline` run against the 156-posting corpus

---

## Acceptance Criteria Verdicts

| AC | Description | Status |
|----|-------------|--------|
| AC #1 | Pipeline order: fetch → parse → C19 filter → URL-dedup → hydrate → LLM-extract → embed → content-dedup → merge → store | PASS |
| AC #2 | New pipeline_runs rows: `llm_extraction` + `embedding` with health_status; title_filter adds `filtered_by_title` count to gmail rows | PASS |
| AC #3 | C22 `select_main` returns canonical-level cards (CanonicalCard), not posting-level | PASS |
| AC #4 | Apply-one-suppress-all: applying LinkedIn variant suppresses canonical from Main on next render | PASS |
| AC #5 | Persistence across restart: state inheritance works via DB JOIN (no in-process state) | PASS |
| AC #6 | Filtered postings (C19) short-circuit; do NOT appear in extraction/embedding counts | PASS |

---

## C22 Quality Criteria (TDD §C22)

| Criterion | Test | Result |
|-----------|------|--------|
| (a) Canonical with ANY linked posting in applied → is_canonical_applied=True | test_true_when_linked_posting_applied | PASS |
| (b) Canonical with ANY linked posting in dismissed → is_canonical_dismissed=True | test_true_when_linked_posting_dismissed | PASS |
| (c) Apply-one-suppress-all: apply LinkedIn → select_main() excludes canonical | test_apply_linkedin_suppresses_canonical_from_main | PASS |
| (d) Re-ingest Indeed variant after apply → does NOT resurface | test_reingest_indeed_does_not_resurface | PASS |
| (e) Restore via C7 → canonical re-appears in Main with both sources | test_unapply_brings_canonical_back_to_main | PASS |

**All 5 pass — 100%.**

---

## Demo Artifact Results

### Live DB State — Before First Run (pre-task)
- `postings`: 183
- `posting_embeddings`: 156
- `canonical_postings`: 0
- `posting_canonical_links`: 0

### First Live Pipeline Run (run_id=7911941b-d006-4f06-8034-cedb1f3ed112)

| Source | Health Status | Counts |
|--------|--------------|--------|
| gmail_linkedin | failed | No OAuth credentials in CLI environment (expected — same as TASK-M2-009) |
| hydrator_linkedin | healthy | No new URLs to hydrate (all 156 already hydrated) |
| llm_extraction | healthy | posting_count=156, success_count=156, parse_failure_count=0, cache_hit_count=156, total_cost_usd=0.0 |
| embedding | healthy | posting_count=0, batch_call_count=0, cache_hit_count=0, total_cost_usd=0.0 |
| dedup_c21 | healthy | 156 decisions made, all action=new |
| dedup_merge_c29 | healthy | new_canonicals_created=156, merges_applied=0, reposts_detected=0 |

### Live DB State — After First Run
- `canonical_postings`: 156 (↑ from 0)
- `posting_canonical_links`: 156 (↑ from 0)
- `merge_kind breakdown`: new_canonical=156

### Second Run (idempotency)
- `new_canonicals_created`: 0
- `merges_applied`: 0
- All 156 posting_canonical_links rows skipped (already_linked check)

### Merge Count vs. Expectations
Pre-task estimate was 7-10 merges based on dry-run analysis. Actual: 0 merges. Reason: all 156 postings are from LinkedIn only (no cross-source pairs). The BLOCK key requires same `(canonical_company, team_or_department, canonical_location)` — with 156 unique roles across different companies, no two postings shared the same BLOCK key at threshold. The 7-10 estimate assumed LinkedIn+Indeed cross-source pairs, but Indeed is deferred to MVP-M1.

---

## Apply-One-Suppress-All Test Result

- Load-bearing M2 invariant test: PASS
- Tested in `tests/state/test_canonical_view.py::TestApplyOneSuppressAll::test_apply_linkedin_suppresses_canonical_from_main`
- Synthetic 2-posting, 1-canonical fixture: applying posting_id=A (LinkedIn variant) → `select_main()` excludes canonical_id entirely
- Restore via unapply: canonical reappears in Main

---

## Cost-Watchdog

- Monthly LLM cost (April 2026): $0.3066 USD
- Threshold: $2.00 (from `config/llm.yaml: monthly_cost_warn_usd`)
- Watchdog fired: NO (cost < threshold)
- LLM extraction this run: $0.00 (156 cache hits, 0 new API calls)

---

## Schema Migrations

1. `pipeline_runs.counts TEXT NULL` — added via `init_db._ensure_pipeline_runs_counts_column()` (idempotent)
2. `postings.canonical_seniority TEXT NULL` — added via `init_db._ensure_postings_canonical_seniority_column()` (bug fix: M2-009 merge.py referenced this column but live DB only had `seniority_band`; adding as nullable column preserves historical data)

---

## Test Counts

| Suite | Passed | Skipped | Failed |
|-------|--------|---------|--------|
| Pre-task baseline | 824 | 10 | 0 |
| Post-task total | 852 | 10 | 0 |
| New tests added | 28 | — | — |

New tests:
- `tests/state/test_canonical_view.py`: 21 tests (C22 quality criteria a-e + edge cases)
- `tests/pipeline/test_orchestrator_m2_e2e.py`: 7 tests (AC #1, #2, #6 coverage)

---

## Conclusion

TASK-M2-010 is complete. All 6 acceptance criteria pass. The pipeline now runs the full M2 sequence end-to-end, the C22 state view correctly implements the apply-one-suppress-all canonical invariant, and the demo artifact successfully populated 156 canonical_postings from the 156-posting corpus on first run.

The schema migration for `postings.canonical_seniority` also resolved a pre-existing M2-009 bug that prevented merge application on the live DB — this was a Minor bug auto-fixed silently per the gate protocol.
