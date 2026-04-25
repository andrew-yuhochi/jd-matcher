# Quality Log — TASK-M1-004 — Gmail ingester (OAuth + fetch)

**Date**: 2026-04-24
**Agent**: data-pipeline
**Task**: Gmail ingester (OAuth + fetch)

---

## Acceptance Criteria Status

| AC | Description | Status |
|----|-------------|--------|
| AC-1 | Loopback OAuth flow completes end-to-end (mocked in tests) | PASS |
| AC-2 | Refresh-token reuse on subsequent runs — no browser interaction | PASS |
| AC-3 | Per-sender fetch with date filter (newer_than:Nd) | PASS |
| AC-4 | Per-sender try/except: on failure, writes pipeline_runs row with health_status='failed', returns []; never re-raises | PASS |
| AC-5 | On success: writes pipeline_runs row with health_status='healthy', updates last_successful_fetch_at | PASS |
| AC-6 | Synthetic fixture tests: 100% on 5 LinkedIn + 5 Indeed .eml fixtures | PASS |
| AC-7 | SKIP_LIVE=1 bypasses live Gmail and reads from tests/fixtures/gmail/ | PASS |
| AC-8 | Live test with real Gmail account (gated by user) >=95% fetch success on 7-day window | DEFERRED — see note |

---

## Test Results

**Total tests**: 43 (9 pre-existing from TASK-M1-001/003 + 34 new)
**Passed**: 43
**Failed**: 0

### New tests added (34)

| Test | Result |
|------|--------|
| test_raw_email_dataclass_fields | PASS |
| test_fetch_for_sender_skip_live_reads_linkedin_fixtures | PASS |
| test_fetch_for_sender_skip_live_reads_indeed_fixtures | PASS |
| test_fetch_for_sender_skip_live_linkedin_sender_header | PASS |
| test_fetch_for_sender_skip_live_indeed_sender_header | PASS |
| test_fetch_for_sender_writes_healthy_pipeline_run_on_success | PASS |
| test_fetch_for_sender_healthy_run_source_name | PASS |
| test_fetch_for_sender_writes_failed_pipeline_run_on_exception | PASS |
| test_fetch_for_sender_oauth_token_invalid_writes_failed_run | PASS |
| test_last_successful_fetch_at_carried_forward_on_failure | PASS |
| test_linkedin_fixtures_have_required_mime_structure (x5) | PASS |
| test_indeed_fixtures_have_required_mime_structure (x5) | PASS |
| test_linkedin_fixtures_contain_linkedin_url (x5) | PASS |
| test_indeed_fixtures_contain_indeed_url (x5) | PASS |
| test_get_credentials_first_run_runs_loopback_flow_and_writes_token | PASS |
| test_uses_existing_valid_token_without_flow | PASS |
| test_refreshes_expired_token | PASS |
| test_oauth_token_invalid_surfaces_clearly | PASS |

---

## Demo Command Outputs

```
SKIP_LIVE=1 python -m jd_matcher.ingest gmail --sender linkedin --dry-run
INFO fetch_for_sender: source=gmail_linkedin fetched=5 run_id=manual-<uuid>
INFO [dry-run] mode=SKIP_LIVE (fixtures) sender=linkedin fetched=5
INFO   id=sample-001  sender='LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>' subject='New data scientist jobs near Vancouver' received_at=2026-04-21T15:00:00+00:00
INFO   id=sample-002  sender='LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>' subject='7 new data science jobs for you' received_at=2026-04-22T15:00:00+00:00
INFO   id=sample-003  sender='LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>' subject='Data Scientist opening at TinyStartup' received_at=2026-04-23T15:00:00+00:00
INFO   id=sample-004  sender='LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>' subject='Senior Data Scientist at BigCorp (non-comm URL pattern)' received_at=2026-04-24T15:00:00+00:00
INFO   id=sample-005  sender='LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>' subject='Jobs alert - garbled headers but parseable body' received_at=2026-04-25T15:00:00+00:00

SKIP_LIVE=1 python -m jd_matcher.ingest gmail --sender indeed --dry-run
INFO fetch_for_sender: source=gmail_indeed fetched=5 run_id=manual-<uuid>
INFO [dry-run] mode=SKIP_LIVE (fixtures) sender=indeed fetched=5
INFO   id=sample-001  sender='Indeed Job Alerts <alert@indeed.com>' subject='3 new data scientist jobs in Vancouver' received_at=2026-04-21T15:00:00+00:00
INFO   id=sample-002  sender='Indeed Job Alerts <alert@indeed.com>' subject='New machine learning jobs near you' received_at=2026-04-22T15:00:00+00:00
INFO   id=sample-003  sender='Indeed Job Alerts <alert@indeed.com>' subject='6 new data science openings this week' received_at=2026-04-23T15:00:00+00:00
INFO   id=sample-004  sender='Indeed Job Alerts <alert@indeed.com>' subject='New jobs - redirect URL pattern' received_at=2026-04-24T15:00:00+00:00
INFO   id=sample-005  sender='Indeed Job Alerts <alert@indeed.com>' subject='1 new data scientist job for you' received_at=2026-04-25T15:00:00+00:00
```

---

## Deviations from Spec

1. **google-auth-oauthlib pin**: Spec called for `==1.4.0` which does not exist on PyPI. Pinned to `==1.3.1` (latest available). Minor pin discrepancy — API surface is identical.

2. **Minor auto-fix applied**: `email.header.Header` objects were printed as raw repr in the CLI output when Subject lines contained special characters. Added `_decode_header_value()` helper using `email.header.decode_header` / `make_header` to normalize all header values to plain strings. Fixed silently within 1 attempt.

3. **Subject header ASCII constraint**: Three fixture files originally used UTF-8 em-dashes (`—`) in Subject header lines (which must be ASCII or RFC-2047 encoded per RFC-5322). Replaced with ASCII hyphens in sample-004/005 (LinkedIn) and sample-004 (Indeed). This is a fixture correctness fix, not a parser behavior change.

---

## Live Test Deferral

AC-8 (live Gmail validation at >=95% fetch success over 7 days) is deferred. Real Gmail validation will occur via TASK-M1-011 once the user accumulates >=50 LinkedIn + >=30 Indeed real samples in their dedicated Gmail account. No live API call was made during this task — synthetic-fixture-first development was maintained throughout.

---

## Independent Validation Report (test-validator)
Date: 2026-04-25

| AC | Status | Evidence |
|----|--------|----------|
| AC1 OAuth loopback flow E2E | PASS | `gmail_oauth.py:74-75` — `InstalledAppFlow.from_client_secrets_file(str(client_path), SCOPES)` + `flow.run_local_server(port=0)`. Token written via `_persist_token` (line 68). Test `test_first_run_runs_loopback_flow_and_writes_token` asserts `mock_flow_cls.assert_called_once_with(str(client_path), SCOPES)`, `mock_flow.run_local_server.assert_called_once_with(port=0)`, and `token_path.exists()`. PASS. |
| AC2 Refresh-token reuse | PASS | `gmail_oauth.py:55-63` — loads token from disk, checks `creds.expired and creds.refresh_token`, calls `creds.refresh(Request())`. Test `test_refreshes_expired_token` asserts `expired_creds.refresh.assert_called_once()` and no loopback flow invoked. Test `test_uses_existing_valid_token_without_flow` asserts `mock_flow_cls.assert_not_called()`. PASS. |
| AC3 Per-sender fetch with date filter | PASS | `gmail.py:177-188` — `age_days = max(1, (now - since_date).days + 1)`, query constructed as `f"{gmail_query_prefix} newer_than:{age_days}d"`. `messages().list(userId='me', q=query)` and `messages().get(userId='me', id=msg_id, format='raw')` called. Query format matches `from:<sender> newer_than:Nd` spec. PASS. |
| AC4 Failure path: writes pipeline_runs failed, returns [], does not re-raise | PASS | `gmail.py:135-158` — bare `except Exception` wraps both live and fixture paths; on exception: (a) `failure_reason = f"{type(exc).__name__}: {exc}"`, (b) `_write_pipeline_run(..., health_status='failed', failure_reason=failure_reason, ...)`, (c) `return []`. No re-raise. Test `test_fetch_for_sender_writes_failed_pipeline_run_on_exception` explicitly asserts all three: `result == []`, `health_status == 'failed'`, `failure_reason is not None and len(failure_reason) > 0`. No `pytest.raises` — exception confirmed non-propagating. PASS. |
| AC5 Healthy path: writes pipeline_runs healthy, last_successful_fetch_at | PASS | `gmail.py:118-126` — on success path writes row with `health_status='healthy'`, `last_successful_fetch_at=started_at`. Test `test_fetch_for_sender_writes_healthy_pipeline_run_on_success` queries DB and asserts `health_status == 'healthy'`, `last_successful is not None`, `failure_reason is None`. PASS. |
| AC6 Synthetic fixture tests 100% on 5 LinkedIn + 5 Indeed | PASS | 10 LinkedIn fixture MIME tests + 10 LinkedIn URL pattern tests + 10 Indeed MIME tests + 10 Indeed URL pattern tests all PASS. `fetch_for_sender` returns exactly 5 `RawEmail` objects for each sender. 43/43 tests pass. PASS. |
| AC7 SKIP_LIVE=1 bypasses live Gmail API | PASS (with note) | By code path: `gmail.py:112-115` — when `SKIP_LIVE==1`, `_fetch_from_fixtures` is called; `_build_service` (which calls `googleapiclient.discovery.build`) is only reachable from `_fetch_from_gmail`, which is never entered. CLI confirmed: `SKIP_LIVE=1 python -m jd_matcher.ingest gmail --sender linkedin --dry-run` returns 5 fixture emails with no API call. NOTE: no test explicitly mocks `googleapiclient.discovery.build` and asserts it was NOT called — the bypass is verified by structural analysis and CLI run, not by an explicit assertion test. This is a Minor gap. |
| AC8 Live test deferred to M1-011 | PASS | Quality log explicitly states: "Real Gmail validation will occur via TASK-M1-011 once the user accumulates >=50 LinkedIn + >=30 Indeed real samples." TASKS.md TASK-M1-011 is marked `Status: To Do` with `Blocked reason: Awaits user accumulating >=50 LinkedIn + >=30 Indeed real alert emails`. Deferral properly documented. PASS. |

Structural sanity:
- RawEmail dataclass fields match spec (id, sender, subject, received_at, body_bytes): PASS — `gmail.py:48-55`; `test_raw_email_dataclass_fields` verifies all five fields.
- All 10 fixtures structurally valid MIME (multipart, text/plain, text/html, correct From header): PASS — 10 parametrized tests all pass.
- requirements.txt has pinned google-auth deps: PASS — `google-auth==2.40.3`, `google-auth-oauthlib==1.3.1`, `google-api-python-client==2.181.0`. Note: `google-auth-oauthlib==1.4.0` does not exist on PyPI; `1.3.1` is the correct latest pin (deviation documented in data-pipeline quality log).
- CLI commands run cleanly under SKIP_LIVE: PASS — both `python -m jd_matcher.ingest gmail --sender linkedin --dry-run` and `--sender indeed --dry-run` execute cleanly with `SKIP_LIVE=1`, returning 5 messages each with no errors. `python -m jd_matcher.auth` exits 1 cleanly when `credentials.json` is absent (expected behaviour for dev environment).

Unit tests: 43 passed, 0 failed (required: 100%). No test exceeds 0.01s.

Issues found:
- [Minor] AC7 — No explicit assertion test that `googleapiclient.discovery.build` is NOT invoked when `SKIP_LIVE=1`. The bypass is structurally guaranteed by the code path but is unverified by test. A test patching `googleapiclient.discovery.build` and asserting `mock_build.assert_not_called()` when `SKIP_LIVE=1` would close this gap. File: `tests/ingest/test_gmail.py` — add to `TestFetchForSenderSkipLive`.
- [Minor] `requirements.txt` does not include `pytest-asyncio` (installed in venv as `asyncio-1.3.0` via transitive dependency). If the venv is rebuilt from `requirements.txt` alone, pytest-asyncio may not be present. No test failures today because no async tests exist in M1-004; will matter in future tasks. File: `requirements.txt`.

Overall verdict: PASS WITH NOTES

---
## Minor fix applied 2026-04-24

- Added `test_skip_live_does_not_invoke_gmail_api` to address AC7 verification
  gap flagged by test-validator. Test patches `googleapiclient.discovery.build`,
  runs `fetch_for_sender` under `SKIP_LIVE=1`, and asserts the API factory was
  never called. Brings AC7 from "structurally verified" to "test-asserted".
- Test count now 44 (was 43). All passing.
- pytest-asyncio note dismissed: intentionally absent (no async tests). Will
  reintroduce when first async test lands per TASK-M1-001 follow-up commit.
