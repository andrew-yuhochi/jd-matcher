# TASK-M1-008 Quality Log — Pipeline orchestrator + non-hideable health logging
Date: 2026-04-25
Evaluator: data-pipeline agent

## AC Results

| AC | Description | Status | Test |
|----|-------------|--------|------|
| AC1 | One pipeline_runs row per source per run, non-null health_status; 3 runs = 12 rows | PASS | `TestMandatoryPersistence::test_three_runs_produce_twelve_rows`, `test_all_rows_have_non_null_health_status`, `test_four_sources_per_run` |
| AC2 | Per-source isolation: hydrator_linkedin failure does not cascade to other sources | PASS | `TestPerSourceIsolation::test_hydrator_linkedin_failure_does_not_cascade_to_gmail_sources`, `test_gmail_indeed_failure_does_not_cascade` |
| AC3 | Health transition emits source_failure event in events table | PASS | `TestSourceFailureEvents::test_source_failure_event_emitted_on_first_failure`, `test_never_run_to_failed_emits_event`, `test_repeated_failure_does_not_duplicate_event` |
| AC4 | Structured JSON log written to logs/pipeline-<run_id>.jsonl; all lines valid JSON; no stdout from pipeline | PASS | `TestStructuredLogging::test_log_file_created_with_run_id`, `test_log_lines_are_valid_json`, `test_log_contains_pipeline_events`, `test_no_stdout_from_pipeline` |
| AC5 | E2E fixture run: 5 LinkedIn + 5 Indeed fixture emails produces N unique postings | PASS | `TestEndToEndFixtureRun::test_e2e_fixture_run_produces_expected_postings` |
| AC6 | Idempotency: second run on same fixture mailbox produces 0 new postings | PASS | `TestIdempotency::test_second_run_produces_zero_new_postings`, `test_idempotency_seen_urls_respected` |

All 6 ACs: PASS. Test suite: 202 passed, 1 skipped (real-data test).

## Drift Decisions

### Drift 1 — Log path
- TDD §C11 Output: `~/.jd-matcher/logs/jd-matcher.log` (single rolling file)
- TASKS.md AC4 + Implementation Checklist: `logs/pipeline-<run_id>.jsonl` (per-run, project-relative)
- Resolution: Used TASKS.md path (`projects/jd-matcher/logs/pipeline-<run_id>.jsonl`).
  Per-run files are easier to find for debugging a specific run. Project-relative keeps logs
  co-located with the project for PoC. TASKS.md ACs are the verification surface, so they
  take precedence. Architect to reconcile TDD at MVP.

### Drift 2 — C10 events emitter dependency
- TDD says `source_failure` events are emitted "via C10".
- Status: C10 (events store/emitter) has NO implementation in M1.
- Resolution: The orchestrator writes `source_failure` events directly to the `events` table
  using raw sqlite3 inserts. The `events` table schema was established in TASK-M1-003 and
  has all the required fields. Documented as M1 simplification; MVP should wire C10 properly.

## Fixture Choices

- Synthetic email fixtures reused from TASK-M1-004 (tests/fixtures/gmail/linkedin/*.eml x10,
  tests/fixtures/gmail/indeed/*.eml x10).
- AC5 uses first 5 fixtures per source (limited via a mock ingester), with expected count
  computed dynamically from what the parsers actually extract — not hardcoded.
- Hydration fixtures (tests/fixtures/hydration/linkedin/sample-*.html) have a coverage gap
  relative to email fixture job IDs. This is expected for SKIP_LIVE mode and is not a bug
  in the orchestrator. The hydration tests (TASK-M1-006) pass all 10/10 synthetic fixtures.

## Implementation Notes

- Sub-run ID pattern: GmailIngester is called with `run_id=f"{run_id}_ingest_{sender}"`
  to avoid conflicting with the orchestrator's canonical pipeline_runs row for the same
  source. Each orchestrator call writes exactly one row per source per run.
- source_failure events: only fired on healthy/never_run → degraded/failed transitions,
  not on repeated failures. This prevents event table spam.
- Logger name: uses explicit string "jd_matcher.pipeline" (not `__name__`) so the file
  handler resolves correctly even when the module runs via `python -m jd_matcher.pipeline`
  (where `__name__` would be `__main__`).

## Real-Data Evaluation
Not applicable at this stage — per TDD §C11 Quality Criteria: "Synthetic only at this
stage. Real-data validation happens through same pipe once user has accumulated emails."
