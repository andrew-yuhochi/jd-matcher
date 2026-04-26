# Quality Log — TASK-M1-009 Web UI Backend

**Date**: 2026-04-25
**Evaluator**: data-pipeline
**Sample type**: Synthetic — seeded SQLite (tmpfile) with 20–23 fixture postings
**Test suite**: `tests/web/test_routes.py` — 27 tests; all PASS

---

## Acceptance Criteria

| AC | Criterion | Status | Test |
|----|-----------|--------|------|
| AC #1 | All 9 endpoints return documented status codes on seeded fixture DB | PASS | `test_get_main_tab_returns_200`, `test_get_applied_tab_returns_200`, `test_get_dismissed_tab_returns_200`, `test_get_healthz_returns_200`, `test_get_source_health_returns_200`, `test_post_apply_returns_200`, `test_post_dismiss_returns_200`, `test_post_restore_returns_200`, `test_post_sync_returns_200_or_500` |
| AC #2 | `/api/source-health` returns 4 entries with correct schema | PASS | `test_source_health_returns_four_entries`, `test_source_health_schema`, `test_source_health_sources_include_all_four`, `test_source_health_never_run_when_no_rows`, `test_source_health_reflects_seeded_canonical_row` |
| AC #3 | Main view does NOT filter by `hydration_status` (failed/partial appear) | PASS | `test_main_view_shows_all_hydration_statuses`, `test_main_view_includes_failed_hydration_postings` |
| AC #4 | Bind address defaults to 127.0.0.1; 0.0.0.0 is rejected with ValueError | PASS | `test_default_host_is_loopback`, `test_zero_zero_host_raises_value_error` |
| AC #5 | State-mutation endpoints are idempotent (double-call = single DB row) | PASS | `test_apply_idempotent`, `test_dismiss_idempotent`, `test_restore_idempotent_when_not_dismissed` |
| AC #6 | All endpoints have integration tests with seeded fixture DB; 100% pass | PASS | 27/27 tests pass |

---

## B1 Guardrail Decision

**Finding**: GmailIngester writes `pipeline_runs` rows using `source = f"gmail_{sender_short}"`,
which is the **same** source value as the orchestrator's canonical rows (`gmail_linkedin`,
`gmail_indeed`). The distinguishing field is `run_id`: ingester sub-runs use
`{orchestrator_run_id}_ingest_{sender}` (e.g. `abc123_ingest_linkedin`), while the
orchestrator writes a clean UUID-only `run_id`.

**Strategy chosen**: `run_id NOT LIKE '%_ingest_%'`

Rationale: We cannot filter by `source` alone (same values). We could filter by the
4 canonical source names (`WHERE source IN (...)`) but that still includes ingester
sub-run rows since they use the same source values. The `_ingest_` substring in the
`run_id` is the only reliable discriminator set by the orchestrator design in
`pipeline.py` (`ingester_run_id = f"{run_id}_ingest_{sender}"`). This pattern is
documented in pipeline.py and is under our control, making it stable.

**Test**: `test_source_health_uses_orchestrator_rows_not_ingester_subrun` — seeds both
row types for `gmail_linkedin` with opposite health_status values and asserts the
orchestrator's value is returned. PASS.

---

## C10 Events

C10 (events emitter) does not exist as a standalone module in M1. The orchestrator
(pipeline.py) writes events directly to the `events` table via `_emit_transition_event_if_needed()`.
This web backend does NOT write to events (user-visible events like `card_viewed`,
`card_marked_applied` are deferred to TASK-M1-010 per UX-SPEC.md §1).

---

## Synthetic Fixture Choices

- 20 base postings: 10 `complete`, 5 `partial`, 5 `failed` hydration status
- Additional postings inserted inline per test for isolation
- All postings use `user_id='default'`
- `pipeline_runs` rows seeded inline per test (not in base fixture) for B1 test

---

## Dependencies Added

| Package | Version | Reason |
|---------|---------|--------|
| fastapi | 0.136.1 | Web framework |
| jinja2 | 3.1.6 | Server-side HTML templating |
| uvicorn | 0.46.0 | ASGI server |
| httpx | 0.28.1 | Required by FastAPI TestClient |
| python-multipart | 0.0.26 | Required for form data parsing |
| starlette | 1.0.0 | FastAPI dependency |
| pydantic | 2.13.3 | Request/response validation |

---

## Auto-Fixes During Self-Validation

1. **Fix #1** (Minor): `test_default_host_is_loopback` used fragile source-text
   string replacement to assert "0.0.0.0" is absent — failed because the rejection
   guard `if host == "0.0.0.0":` legitimately contains that string. Fixed by
   simplifying the test to inspect the default literal `"127.0.0.1"` directly and
   use `monkeypatch.delenv` to verify env-var default.
