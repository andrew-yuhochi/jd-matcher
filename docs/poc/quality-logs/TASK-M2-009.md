# Quality Log — TASK-M2-009

**Task**: Canonical Merge + Repost Detector (C29 + C30)
**Date**: 2026-04-29
**Agent**: data-pipeline
**Components**: C29 (merge.py), C30 (repost.py), pipeline.py Phase 5

---

## Scope

C29 applies DedupDecision outputs to `canonical_postings` and `posting_canonical_links`. C30 retags merge decisions as reposts when the 30-day threshold is met and emits events. The pipeline orchestrator gains Phase 5 that wires C30→C29 after Phase 4's decision collection.

---

## Methodology

All tests use isolated `tmp_path` SQLite fixtures — no writes to the live DB. 8 C29 invariants + 5 C30 invariants + 1 demo integration test = 17 new tests. Sample type: Synthetic (deterministic). Pass standard: 100%.

---

## Acceptance Criteria Verdicts

| # | AC | Status | Evidence |
|---|-----|--------|----------|
| 1 | action="new": INSERT canonical + link (merge_kind='new_canonical') | PASS | `TestNewCanonicalPath::test_new_creates_one_canonical_one_link` |
| 2 | action="merge": INSERT link (content_dedup); UPDATE canonical (MIN first_seen, MAX last_seen, JD swap, sources_summary) | PASS | TestFirstSeenMerge, TestLastSeenMerge, TestFullJdSwap, TestSourcesSummary |
| 3 | postings table NEVER modified on merge | PASS | Demo integration test verifies `n_postings == 2` after 2 merges |
| 4 | sources_summary correctly appends source values | PASS | `TestSourcesSummary::test_new_source_appended` → `["linkedin", "indeed"]` |
| 5 | Transactional — partial failure rolls back | PASS | `TestTransactionalRollback::test_link_insert_failure_rolls_back_canonical_update` |
| 6 | Repost detection: ≥30 days → retag 'repost' | PASS | TestRepostPositive (45 days), TestRepostThresholdEdge (exactly 30 days) |
| 7 | On repost: emit posting_reposted event to events table | PASS | Both positive repost tests verify `_count_repost_events(db) == 1` |
| 8 | Inactive/Expired bypass: C30 never retags action='new' | PASS | `TestInactiveExpiredBypass` + `TestNewDecisionPassthrough` |
| 9 | 8 merge invariants + 5 repost invariants | PASS | 12 merge tests (8 invariants + 2 per-class extensions) + 5 repost tests |

---

## C29 Merge Invariant Results (8 quality criteria)

| # | Invariant | Outcome | Evidence |
|---|-----------|---------|----------|
| (a) | action='new' → 1 canonical + 1 link (merge_kind='new_canonical', score=1.0) | PASS | `test_new_creates_one_canonical_one_link` |
| (b) | action='merge' does NOT modify canonical_title/top_skills/role_summary | PASS | `test_merge_does_not_change_canonical_fields` — snapshot before/after verified |
| (c) | first_seen = MIN: 2024-01-01 candidate + 2024-03-01 canonical → 2024-01-01 | PASS | `test_older_candidate_updates_first_seen` |
| (d) | last_seen = MAX: 2024-12-01 candidate + 2024-03-01 canonical → 2024-12-01 | PASS | `test_newer_candidate_updates_last_seen` |
| (e) | full_jd swap: 11% longer swaps in; 5% longer does NOT | PASS | `test_11_percent_longer_swaps_in` + `test_5_percent_longer_does_not_swap` |
| (f) | sources_summary append: Indeed → LinkedIn-only → `["linkedin", "indeed"]` | PASS | `test_new_source_appended` |
| (g) | State inheritance: applied seed → merged variant → excluded from C22 main view | PASS | `test_applied_canonical_excluded_from_main` — SQL join pattern verifies exclusion |
| (h) | Transactional rollback: link insert failure → canonical unchanged | PASS | `test_link_insert_failure_rolls_back_canonical_update` — patch verified |

---

## C30 Repost Invariant Results (5 quality criteria)

| # | Invariant | Outcome | Evidence |
|---|-----------|---------|----------|
| (a) | Positive repost: merged_at + 45 days → 'repost' + 1 event | PASS | `test_45_days_later_is_repost` |
| (b) | Within-window: merged_at + 14 days → 'content_dedup' + 0 events | PASS | `test_14_days_later_is_not_repost` |
| (c) | Threshold edge: merged_at + exactly 30 days → 'repost' (>= semantics) | PASS | `test_exactly_30_days_is_repost` |
| (d) | action='new' pass-through: unchanged + 0 events | PASS | `test_action_new_is_passthrough` |
| (e) | Inactive/Expired bypass: action='new' from C21 filter → no retag, 0 events | PASS | `test_inactive_canonical_filtered_by_c21_arrives_as_new` |

---

## Demo Artifact Result

`TestDemoIntegration::test_two_postings_one_canonical_two_links_postings_preserved`:
- P1 (first_seen=2024-01-15, source=linkedin): action='new' → canonical_id created
- P2 (first_seen=2024-03-01, source=indeed): action='merge' → linked to same canonical
- **canonical_postings**: 1 row (PASS)
- **posting_canonical_links**: 2 rows (PASS)
- **postings**: 2 rows — both originals preserved, APPEND-ONLY invariant holds (PASS)
- **canonical.first_seen**: `2024-01-15` = MIN(2024-01-15, 2024-03-01) (PASS)

---

## Pipeline Orchestrator Integration

Phase 5 ("Merge apply (C29+C30)…") was added after Phase 4 in `run_pipeline()`.

Execution order: Phase 1 (Gmail) → Phase 2 (Hydration) → Phase 3 (C20 Embedding) → Phase 4 (C21 Decide) → Phase 5 (C30+C29 Apply).

Phase 4 now collects `pending_decisions: list[tuple[int, DedupDecision]]` and skips already-linked postings (idempotency). Phase 5 iterates pending_decisions: `detect_repost()` → `apply_decision()`.

`PipelineRunSummary` gains: `merges_applied`, `new_canonicals_created`, `reposts_detected`.

A new `pipeline_runs` row (`source='dedup_merge_c29'`) is written at the end of Phase 5. Five existing orchestrator tests were updated to reflect the count change (3 → 4 sources per run).

---

## Note on Real-Data Validation

C29/C30 real-data merge testing will occur automatically on the next `run_pipeline()` call against the live DB, once postings have accumulated and C21 produces merge decisions. No real postings have been processed through C29 yet (this is the first M2 task to write `canonical_postings`). Real-data validation is scoped to the post-M2-009 pipeline run — the snapshot at `~/.jd-matcher/snapshots/20260429-1442-pre-m2-009.db` is the clean baseline.

---

## Test Suite Summary

| Metric | Count |
|--------|-------|
| New tests added | 17 |
| Tests updated (row count updates) | 5 |
| Total tests passing | 824 |
| Total tests skipped | 10 |
| Failures | 0 |

**Verdict: PASS — all 9 ACs verified, all 13 invariants pass, demo artifact confirmed.**
