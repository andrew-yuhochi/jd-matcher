# Quality Log — TASK-M1-005c: Per-email ingest log + report CLI

**Date**: 2026-04-26
**Evaluator**: data-pipeline agent
**Test suite result**: 291 passed, 2 skipped, 0 failed (all tests including 45 new)

---

## Acceptance Criteria Results

| AC | Description | Test | Result |
|----|-------------|------|--------|
| AC #1 | `email_ingest_log` table created via idempotent `init_db()` | `tests/db/test_email_ingest_log_schema.py` (6 tests) | PASS |
| AC #2 | C3 inserts one row per fetched email with metadata populated; counters default to 0 | `tests/ingest/test_gmail_log_writer.py` (5 tests) | PASS |
| AC #3 | C4 updates `urls_extracted_count` and `urls_new_count` | `tests/parse/test_email_log_url_counters.py` (4 tests) | PASS |
| AC #4 | C5 updates `postings_hydrated_count` / `postings_hydration_failed_count` per posting | `tests/hydrate/test_email_log_hydration_counters.py` (5 tests) | PASS |
| AC #5 | All writers use canonical orchestrator `pipeline_run_id`; DISTINCT count == 1 per invocation | `tests/test_pipeline_log_integration.py::test_ac5_single_distinct_pipeline_run_id` | PASS |
| AC #6 | `python -m jd_matcher.report ingest` renders markdown table to stdout | `tests/test_report_cli.py::TestMarkdownOutput` (5 tests), `TestCmdIngest` (5 tests) | PASS |
| AC #7 | `--since YYYY-MM-DD` filters to rows with `received_at >= date` | `tests/test_report_cli.py::TestSinceFilter` (3 tests) | PASS |
| AC #8 | `--source X` filters to rows where `source = X` | `tests/test_report_cli.py::TestSourceFilter` (3 tests) | PASS |
| AC #9 | `--format csv` outputs valid CSV parseable by `csv.DictReader` | `tests/test_report_cli.py::TestCsvOutput` (5 tests) | PASS |
| AC #10 | Aggregate totals match column sums; integration test: 5+5 emails → log rows with non-zero counters | `tests/test_report_cli.py::TestCsvOutput::test_csv_totals_match_column_sums`, `tests/test_pipeline_log_integration.py::test_ac10_counters_updated_after_pipeline_run` | PASS |

---

## Threading Approach: Option B (Orchestrator Side-Mapping)

**Decision**: Option B — build a `{url: gmail_message_id}` dict in `_run_gmail_source` during the parse loop, return it as part of `SourceResult.url_to_gmail_id`, merge across all Gmail source results in `run_pipeline`, pass into `_run_hydrator_source`.

**Rationale**: Option A (carry `gmail_message_id` in `ParsedPosting` or a new `ExtractedURL` dataclass) would require modifying `ParsedPosting` (which is exported from `linkedin_email.py` and used by 8+ test files and by `url_dedup.py`). The cascade of signature changes would be large and risky. Option B achieves the same result with zero changes to `ParsedPosting`, `parse_linkedin`, `parse_indeed`, or `url_dedup.py`. The only callers affected are internal to `pipeline.py`.

**Data flow**: `raw_email.id` (the Gmail message ID from `RawEmail.id`) is used as `gmail_message_id`. During the parse loop in `_run_gmail_source`, for each posting extracted from an email, `url_to_gmail_id[posting.url] = raw_email.id` is recorded before dedup. This means even "seen" URLs retain their email association in the mapping (for future hydration accounting if they are re-queued).

---

## Orchestrator API Changes

| File | Change | Callers Affected |
|------|--------|-----------------|
| `src/jd_matcher/ingest/gmail.py` | Added `canonical_run_id: str | None = None` param to `fetch_for_sender` | `pipeline.py` (passes `canonical_run_id=run_id`); test mocks in `test_orchestrator.py` (updated to accept new kwarg) |
| `src/jd_matcher/pipeline.py` | Added `url_to_gmail_id: dict` to `SourceResult`; `_run_gmail_source` now builds + returns the mapping; `_run_hydrator_source` accepts + consumes it; `run_pipeline` merges mappings across Gmail sources | `test_orchestrator.py` mocks updated (3 classes, all added `canonical_run_id=None` to `fetch_for_sender`) |
| `src/jd_matcher/pipeline.py` | Added `from jd_matcher.db.email_ingest_log import increment_hydration, update_url_counts` | No external callers; internal imports |

---

## AC #5 Verification Detail

Integration test `test_ac5_single_distinct_pipeline_run_id` performs:
```sql
SELECT DISTINCT pipeline_run_id FROM email_ingest_log
```
After one `run_pipeline()` invocation with 5 LinkedIn + 5 Indeed fixture emails:
- Result: 1 row
- Value: matches `summary.run_id` (the orchestrator's canonical UUID)
- Confirms: the `_ingest_<sender>` sub-run-id is NOT written to `email_ingest_log`

---

## Auto-Fixes Applied During Self-Validation

1. **`test_init_db_creates_all_8_tables` failure** (Minor): The table count assertion in `tests/db/test_init_db.py` expected 8 tables; adding `email_ingest_log` made it 9. Updated `ALL_TABLES` set.

2. **`test_gmail_indeed_failure_does_not_cascade` + `test_e2e_fixture_run_produces_expected_postings` failures** (Minor): Two pre-existing mock classes (`FaultyIngester`, `_LimitedIngester`) in `tests/pipeline/test_orchestrator.py` had `fetch_for_sender` signatures without `canonical_run_id`, causing `TypeError` when the orchestrator passed the new keyword argument. Updated both mock signatures to accept `canonical_run_id: str | None = None`.

Total auto-fixes: 3 (all Minor tier, all resolved in first attempt).

---

## Unexpected Findings

- `RawEmail.id` is set to the Gmail message ID from the API (or the `.eml` filename stem for fixtures). Fixtures use names like `sample-001`, which serves as a stable unique ID for `email_ingest_log.gmail_message_id` in tests. No collision risk since each fixture file has a distinct stem.
- The `postings_created_count` column (TDD §1.2a) equals `urls_new_count` in M1 because `register_new()` creates exactly one posting per new URL. This equality is by design and is asserted in `test_ac10_counters_updated_after_pipeline_run`.
- Indeed fixture emails (sample-001 through sample-005) produce 0 extracted URLs in synthetic runs because the fixture body does not contain parseable Indeed job URLs with `jk=` parameters. Their `email_ingest_log` rows are still inserted with 0 counters, demonstrating that C3 fires regardless of parse outcome.
