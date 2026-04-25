# Quality Log — TASK-M1-007 State Manager

**Date**: 2026-04-25
**Component**: C7 — State Manager (applied / dismissed / restore)
**Evaluation type**: Deterministic, synthetic only
**Pass threshold**: 100% (per TDD)

---

## Acceptance Criteria Evaluation

| AC | Status | Test |
|----|--------|------|
| `mark_applied(posting_id)` creates a row in `applied` with current timestamp and `status='Applied'` (default) | PASS | `test_mark_applied_creates_row_with_applied_status`, `test_mark_applied_sets_applied_at_and_status_updated_at` |
| `dismiss(posting_id)` creates a row in `dismissed` with current timestamp; idempotent (re-dismiss is no-op) | PASS | `test_dismiss_creates_dismissed_row`, `test_dismiss_idempotent` |
| `restore(posting_id)` deletes from `dismissed`; if not in dismissed, no-op | PASS | `test_restore_deletes_dismissed_row`, `test_restore_noop_when_not_dismissed` |
| `main_view_postings()` returns postings WHERE `id NOT IN applied AND id NOT IN dismissed` — verified against fixture | PASS | `test_main_view_excludes_applied_and_dismissed`, `test_main_view_returns_posting_objects`, `test_main_view_ordered_by_first_seen_desc` |
| State persists across server restart (integration test closes connection, reopens, reads) | PASS | `test_state_persists_across_connection_restart` |
| `auto_remove_stale_applied(cutoff_date)` exists and is unit-tested — not auto-triggered in M1 | PASS | `test_auto_remove_stale_applied_removes_old_rows`, `test_auto_remove_stale_applied_preserves_offer_status`, `test_auto_remove_stale_applied_returns_count`, `test_auto_remove_stale_applied_noop_when_nothing_stale` |

**Result: 6/6 ACs PASS — 100% pass rate**

---

## Test Run Summary

```
15 passed, 0 failed (tests/state/test_state_manager.py)
184 passed, 1 skipped, 0 failed (full suite)
```

---

## Naming Reconciliation

TASKS.md names were used as the canonical public API, per task instructions:

| TASKS.md name | TDD §C7 name | Decision |
|---------------|-------------|----------|
| `mark_applied` | (implied: apply) | TASKS.md |
| `dismiss` | (implied: dismiss) | TASKS.md |
| `restore` | (implied: restore) | TASKS.md |
| `main_view_postings` | `select_main(user_id)` | TASKS.md (+ optional `user_id` param) |
| `auto_remove_stale_applied(cutoff_date)` | `purge_stale_applied(user_id)` | TASKS.md (+ optional `user_id` param) |

---

## Schema Observations

- `user_id` exists on all relevant tables (`applied`, `dismissed`, `postings`) with default `'default'`. All public functions accept `user_id` as an optional keyword argument defaulting to `'default'`. This is an M1 simplification (single-user); multi-user is a Beta concern.
- The TDD §C7 spec references `auto_remove_at` as a column on `applied`, but the actual M1 schema does not have this column. `auto_remove_stale_applied` uses `applied_at < cutoff_date` instead — functionally equivalent for M1, and the cutoff boundary is caller-supplied. Flagged as M1 simplification.
- `StateTransition` is implemented as a `dataclass` rather than a Pydantic model, matching the project-wide pattern (Pydantic is not installed; all other models use stdlib dataclasses).

---

## Sample Selection

Synthetic only — fixture-driven tests with in-memory SQLite databases via `tmp_path`. No real data evaluation required per TDD §C7 Quality Criteria ("Synthetic only — fixture-driven end-to-end tests + server-restart integration test").

---

## Connection Pattern

Caller-owned connection pattern (matching `url_dedup.py`): when `conn` is passed, the function never calls `commit()` — the caller commits. The restart test explicitly calls `conn1.commit()` before `conn1.close()` to simulate a clean server shutdown.
