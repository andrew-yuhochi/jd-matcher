# Quality Log — TASK-M1-010: Web UI frontend + events instrumentation

Date: 2026-04-26
Agent: data-pipeline
Test suite: `SKIP_LIVE=1 python -m pytest -v` — 353 passed, 2 skipped, 0 failed

---

## Acceptance Criteria Verification

| AC | Description | Test(s) | Result |
|----|-------------|---------|--------|
| #1 | Three tabs render correctly with seeded fixture postings | `test_main_tab_has_three_tab_links`, `test_main_tab_has_data_tab_attributes`, `test_main_tab_shows_seeded_cards`, `test_applied_tab_renders_200`, `test_dismissed_tab_has_search_box` | PASS |
| #2 | Keyboard shortcuts work (j/k/e/d/a/o/1/2/3/?/Esc) | Static JS analysis in `test_keyboard_handler.py` + API-level backend endpoint tests. Browser interaction: MANUAL REQUIRED at M1 demo. | PASS (structural) / MANUAL REQUIRED (browser) |
| #3 | Sub-bar shows 4 health badges with correct data-source attrs | `test_subbar_has_four_badges`, `test_subbar_badges_have_badge_ids` | PASS |
| #4 | Health badges NOT dismissible (LOAD-BEARING) | `test_badges_have_no_close_button`, `test_badges_have_no_x_character_inside_badge_span`, `test_app_js_no_close_button_added_to_badges` | PASS |
| #5 | Hover on non-green badge shows failure_reason tooltip | `test_failed_badge_has_failure_reason_in_title` (verifies /api/source-health carries failure_reason; title= populated by JS on page load) | PASS |
| #6 | hydration_status=partial/failed cards show ⚠ indicator + all shortcuts work (LOAD-BEARING) | `test_hydration_failed_cards_present_in_main`, `test_complete_hydration_card_has_no_warning` | PASS |
| #7 | Events instrumentation writes correct row per interaction | `test_events_endpoint.py` — 23 tests including parametric M1 event types | PASS |
| #8 | Structural DOM tests — 100% pass | All 61 new tests: 14 DOM + 23 events + 24 keyboard handler | PASS (61/61) |

---

## Playwright vs Manual Smoke

**Path taken: manual smoke documented, Playwright NOT installed.**

Playwright (`pytest-playwright`) is not installed in this environment and requires browser binaries not available on this machine. Per TDD §C9 quality (a): "manual smoke is explicitly allowed."

Structural keyboard handler tests verify:
- app.js exists and is served at `/static/js/app.js`
- All required key handlers are present in source (j/k/e/d/a/o/1/2/3/?/Esc)
- All event types are emitted (card_dismissed, card_marked_applied, tab_switched, session_start/end, card_viewed, card_expanded, card_restored)
- IntersectionObserver is used for card_viewed tracking
- time_to_decide_ms is computed and included in card_dismissed/card_marked_applied
- dismissing + applying CSS classes are applied for animations
- Backend endpoints (dismiss/apply/events) are verified via API-level integration tests

**Browser verification required at M1 demo (TASK-M1-012):**
1. j/k focus ring movement
2. e expand/collapse
3. d 180ms slide-left animation (CSS transition: transform 180ms ease-in)
4. a 150ms fade-out (CSS transition: opacity 150ms ease-out)
5. o opens URL in new tab
6. 1/2/3 tab switch + tab_switched event emitted
7. ? cheatsheet modal
8. Esc priority-stacked close

---

## Session ID Approach

Session ID is generated **client-side** using `crypto.randomUUID()` on page load and stored in `sessionStorage`. It is sent in the JSON **request body** of every `POST /api/events` call as `session_id`. The server reads it from the Pydantic `EventWriteRequest.session_id` field and writes it to `events.session_id`.

Rationale: simpler than cookie management, more explicit than a custom header, and forward-compatible with M4 analytics grouping (30-minute idle window derivation per UX-SPEC §4).

---

## Auto-fixes During Self-Validation

1 Minor auto-fix: `test_app_js_no_close_button_added_to_badges` — initial regex captured the `/* NO close button */` comment in `updateBadge()` and incorrectly flagged it. Fixed the test to check for actual DOM-injection patterns (innerHTML, createElement, appendChild) rather than the word "close" in any context.

---

## Subjective UX Decisions (flagged for M1 demo)

1. **Card density**: 8px padding, 0.5rem gap between cards. Single-column layout. User should verify this feels dense enough without being cramped at typical display sizes.

2. **Animation feel**: 180ms slide-left + 100ms collapse for dismiss; 150ms fade-out for apply. Pure CSS transitions — no library. User should verify this feels snappy vs. jarring.

3. **Source-health badge initial state**: badges render as grey `never_run` on page load; JS fetches `/api/source-health` and updates colors + tooltips asynchronously. There is a brief flash of grey (sub-100ms) before the real status shows. User to confirm this is acceptable.

4. **Action buttons visibility**: `btn-apply` and `btn-dismiss` are hidden by default (keyboard-driven), revealed on hover or card-focused state. Screen readers can still reach them (not `display:none`, just `visibility:hidden`). User should verify accessibility is acceptable for PoC.

5. **`o` key**: opens the `card-apply-link` (`<a>` with source URL). Cards without a source URL in `posting_sources` will have an empty `data-url` attr and the `o` key is a no-op. This is expected at M1 where source URLs are always present for real data.

---

---

## Real-data validation findings (fix-forward commit on top of 56592a3) — 3 bugs fixed

Discovered during first live Gmail sync against the user's real account (real OAuth, production DB).
Validated against 46 real `.eml` fixtures in `tests/fixtures/real/`.

### Bug 1 — Form-submit fallback in main.html showed raw JSON

**Root cause**: `templates/main.html` had a `<form action="/sync" method="post">` in the empty-state. When the user clicked "Run sync now", the browser navigated to `/sync` and rendered raw JSON instead of using the JS-driven fetch path.

**Fix**: Removed the `<form>` and submit button from `main.html`. The empty-state paragraph remains; the canonical sync trigger is `btn-sync` in `base.html` (always visible in the header, driven by `app.js` fetch).

**Test added**: `tests/web/test_frontend_dom.py::test_no_form_action_sync_in_main_tab` — asserts `b'action="/sync"' not in response.content` on GET `/`.

---

### Bug 2 — GmailIngester double-wrote pipeline_runs with ADC failure

**Root cause**: When the orchestrator calls `GmailIngester.fetch_for_sender` with `canonical_run_id` set, the ingester was still writing its own `pipeline_runs` row. The internal `run_id` was `{canonical_run_id}_ingest_{sender}`. These internal writes attempted to call the Gmail API using Application Default Credentials (ADC), which the user doesn't have configured. This produced phantom `failed` rows in `pipeline_runs` with `DefaultCredentialsError` as the failure reason, in addition to the orchestrator's canonical healthy row.

**Fix**: `GmailIngester.fetch_for_sender` now skips the internal `_write_pipeline_run` call on both success and failure paths when `canonical_run_id is not None`. The orchestrator is the sole writer of the canonical `pipeline_runs` row. The standalone CLI path (`canonical_run_id=None`) is unaffected — it still writes its own row.

**Side effects verified**:
- `/api/source-health` filter `WHERE run_id NOT LIKE '%_ingest_%'` still works (no such rows for orchestrator-driven runs).
- Standalone CLI invocations still write correctly.
- Existing `TestPipelineRunsHealthy` tests call without `canonical_run_id`, so they still exercise the write path and are unaffected.

**Test added**: `tests/test_pipeline_log_integration.py::TestPipelineIngestLogIntegration::test_no_ingest_sub_run_rows_written_by_orchestrator` — asserts `count(*) WHERE run_id LIKE '%_ingest_%' = 0` and `total pipeline_runs rows = 4` after a full orchestrated run.

---

### Bug 3 — Indeed sender filter didn't match real Indeed emails

**Root cause**: `_SENDER_FILTERS["indeed"]` was `"from:alert@indeed.com"`. Real Indeed alert emails come from `donotreply@jobalert.indeed.com` (verified in 29/46 real fixtures). The old filter matched 0 of the user's Indeed emails; ~63% of alert volume was silently dropped.

**Fix**: Changed filter to `"from:@jobalert.indeed.com"` (loose domain-suffix pattern). Chosen over the exact `donotreply@` address to catch future addresses on the same domain (e.g. `weekly-digest@jobalert.indeed.com`).

**Test added**: `tests/ingest/test_gmail.py::TestIndeedSenderFilterMatchesRealFixtures` — parameterized over all 46 real `.eml` fixtures; non-Indeed fixtures skip automatically. 29 Indeed fixtures verified all pass. Guarded by `@pytest.mark.skipif` so CI without `tests/fixtures/real/` doesn't break.

---

**Suite result after fixes**: `SKIP_LIVE=1 python -m pytest tests/` — 397 passed, 19 skipped, 0 failed (up from 353 passed pre-M1-010).

**Note**: This validation is essentially M1-011 done early. M1-011 will re-validate once the user retriggers a live sync with the corrected Indeed filter to confirm real Indeed emails flow through end-to-end.

---

---

## Real-data validation findings — third pass (fix-forward on top of 1833e54) — UI hidden attr, WAL mode, Indeed stealth + JSON-LD

**Date**: 2026-04-27

Three M1-blocking bugs discovered during real-data validation against user's live Gmail (54+ ingested postings). Expected post-fix: LinkedIn 65/65 + Indeed 16/16 = ~100% hydration vs 26% before.

### Fix 1 — `_card.html` `hidden` attribute prevented expand/collapse

**Root cause**: `<div class="card-expanded-body" hidden>` — the HTML `hidden` attribute equals `display:none !important` and overrides `.card.expanded .card-expanded-body { display: block; }` in CSS because CSS doesn't use `!important`. Pressing `e` adds `.expanded` to the card but the description stayed invisible.

**Fix**: Removed the `hidden` attribute. CSS already has `.card-expanded-body { display: none; }` as default — `hidden` was redundant and broke the toggle.

**Test added**: `tests/web/test_frontend_dom.py::test_card_expanded_body_has_no_hidden_attribute` — parses rendered HTML, asserts `.card-expanded-body` has no `hidden` attribute.

---

### Fix 2a — SQLite WAL mode in `init_db`

**Root cause**: Default SQLite rollback-journal mode blocks readers while a writer holds the lock. During the hydrator's 30s rate-limiter sleep window, the web UI (uvicorn) opens a read transaction. The hydrator's next write hit the lock → `OperationalError: database is locked`.

**Fix**: Added `PRAGMA journal_mode=WAL;` and `PRAGMA synchronous=NORMAL;` to `init_db()` before DDL. WAL allows concurrent readers + 1 writer.

**Test added**: `tests/test_pipeline_log_integration.py::test_init_db_enables_wal_mode` — verifies `PRAGMA journal_mode;` returns `wal` after `init_db()`.

---

### Fix 2b — Per-URL exception handling in hydrator loop

**Root cause**: `_run_hydrator_source` had no per-URL try/except. The first `OperationalError` (DB lock) aborted the outer `try` block, catching in the outer `except Exception` which wrote `pipeline_runs health_status='failed'` and returned early. 44 remaining LinkedIn URLs were never attempted.

**Fix**: Added per-URL try/except inside the hydrator loop. `sqlite3.OperationalError` (DB lock) logs a warning and continues to next URL. Generic `Exception` logs an error and continues. If ALL URLs throw exceptions, source health is still set to `failed` (preserving the transition event for monitoring).

**Tests added**: `TestHydratorPerUrlExceptionIsolation` — two tests: `test_db_lock_on_one_url_does_not_abort_batch` (3rd of 5 URLs raises `OperationalError` → ≥4 hydrated) and `test_generic_exception_on_one_url_does_not_abort_batch` (2nd URL raises `RuntimeError` → batch continues).

---

### Fix 3 — Indeed hydrator: full M1-005b stealth stack + Session reuse

**Root cause**: `_fetch_live` used `requests.get(..., headers={"User-Agent": _BROWSER_UA})` — missing `Referer`, `Accept`, `Accept-Language`, and all four `Sec-Fetch-*` headers. Cloudflare's browser-check heuristic requires the full header set; without `Sec-Fetch-*` headers specifically, 100% of Indeed viewjob URLs return 403.

**Fix**: Replaced bare `requests.get()` with `requests.Session()` + `session.headers.update(_STEALTH_HEADERS)`. `_STEALTH_HEADERS` has all 8 header items (9th = Session reuse itself):
- `User-Agent`: Chrome/124 on macOS
- `Referer`: https://mail.google.com/
- `Accept`: full browser accept string
- `Accept-Language`: en-US,en;q=0.9
- `Sec-Fetch-Site`: cross-site
- `Sec-Fetch-Mode`: navigate
- `Sec-Fetch-Dest`: document
- `Sec-Fetch-User`: ?1

Also changed `timeout=10` → `timeout=30` and added `allow_redirects=True`. JSON-LD and DOM fallback parsing already correct — no changes needed there.

**Tests added** in `tests/hydrate/test_indeed_hydrator.py`:
- `test_stealth_headers_all_nine_items_present` — verifies all 8 keys are in `_STEALTH_HEADERS`
- `test_fetch_live_uses_session_with_stealth_headers` — mocks Session, verifies `headers.update(_STEALTH_HEADERS)`, `allow_redirects=True`, `timeout=30`, and `session.close()` are all called
- `test_json_ld_extraction_all_fields` — JSON-LD fixture → all 5 fields extracted
- `test_fallback_to_job_description_text_div` — DOM-only fixture → `full_jd` extracted
- `test_neither_json_ld_nor_dom_returns_failed` — empty page → `hydration_status='failed'`

---

### Live verification (3 real Indeed URLs)

Ran new hydrator against 3 real `ca.indeed.com/viewjob?jk=...` URLs from the user's DB:

| URL (jk) | Status | Title | JD length |
|----------|--------|-------|-----------|
| 1cf8599d401f263a | complete | Data Governance and Analytics Senior Systems Analyst | 12,157 chars |
| 6030f31547cafc15 | complete | Senior QA Analyst - Platform Data Integration | 9,051 chars |
| fbb4872b97dbe685 | complete | Software Engineer, iOS Core Product | 5,093 chars |

**3/3 complete** (100%) — all via JSON-LD path. Previously 0/3 (Cloudflare 403). Above M1's ≥95% bar.

### Test suite result

411 passed, 19 skipped, 0 failed (up from 402 passed pre-fix-3-pass).

New tests added: 9 total
- 1 DOM: `test_card_expanded_body_has_no_hidden_attribute`
- 1 WAL: `test_init_db_enables_wal_mode`
- 2 pipeline: `TestHydratorPerUrlExceptionIsolation` (2 tests)
- 5 Indeed hydrator: stealth headers + JSON-LD + DOM fallback + neither + session

---

## Tag chip / salary / CV chip — NOT rendered at M1

Confirmed absent from `_card.html`. The template renders exactly:
- Line 1: title — company (bold) + optional ⚠ warning
- Line 2: location · Apply link (if URL present)
- Line 3: First seen date
- Action buttons (hidden by default)
- Expanded body (hidden until `e` pressed)

No tag chips, salary fields, or CV chips rendered. Per TDD §C9 and UX-SPEC §1 explicit absence.

---

## Real-data validation findings — second pass (fix-forward on top of bf501d5) — credentials propagation + error propagation

**Date**: 2026-04-26
**Commit**: see git log

### Bug 3 (Fix 1) — /sync endpoint not loading OAuth credentials

Root cause: `routes.py /sync` called `run_pipeline()` with no `credentials` argument (defaults to `None`). The orchestrator passed `None` to `GmailIngester`, which deferred credential loading to the Google library's Application Default Credentials — failing silently because Bug 2's fix (bf501d5) had removed the `pipeline_runs failed` write path for orchestrator-driven calls.

Fix: `/sync` now loads credentials via `get_credentials()` (same pattern as the CLI `__main__.py`) before calling `run_pipeline`. Returns 503 if `credentials.json` is missing; 401 if token is invalid.

`SKIP_LIVE=1` check is wired first — test mode skips credential loading entirely, preserving existing test behavior.

### Bug 4 (Fix 2) — GmailIngester swallowing exceptions when called by orchestrator

Root cause: the `except` branch in `fetch_for_sender` always returned `[]` regardless of whether `canonical_run_id` was set. After Bug 2's fix correctly skipped the internal `pipeline_runs` write, this meant: exception raised inside → logged but swallowed → orchestrator sees `emails=[]`, no exception → writes `pipeline_runs healthy`. End result: every web-triggered sync with bad credentials reported "healthy with 0 new postings."

Fix: when `canonical_run_id is not None` (orchestrator-driven call), the `except` branch now re-raises. The orchestrator's existing `try/except` in `_run_gmail_source` catches it and writes the canonical `failed` row.

### Orphan rows decision — INSERT OR REPLACE

The diagnostic test earlier today inserted 54 rows into `email_ingest_log` with `pipeline_run_id="manual-db1051e4-..."`. With `INSERT OR IGNORE`, these would persist forever attributed to that manual run — the report CLI for the next real sync would not show those 54 emails.

Decision: changed `insert_email_log` to `INSERT OR REPLACE`. On the next real sync, the same 54 `gmail_message_id` values will update their rows to the new orchestrator `run_id` and `ingested_at`. The report CLI will correctly attribute them to the latest run.

Trade-off acknowledged: `INSERT OR REPLACE` resets URL/hydration counter columns to 0 on replace (SQLite REPLACE = DELETE + INSERT). Those counters are re-written by the C4 and C5 hooks immediately after, so the final state is correct. Only a very narrow race (crash between INSERT and C4 write) would leave counters at 0, and that's acceptable at PoC scale.

### Test counts

- Before: 397 passed, 19 skipped
- After: 402 passed, 19 skipped, 0 failed
- New tests added:
  - `test_post_sync_skip_live_no_credentials_needed` — /sync with SKIP_LIVE=1 passes credentials=None
  - `test_post_sync_missing_client_secrets_returns_503` — /sync without credentials.json → 503
  - `test_fetch_failure_writes_failed_pipeline_runs` — orchestrator exception → failed pipeline_runs rows
  - `test_fetch_failure_summary_shows_zero_new_postings` — exception → total_new_postings==0, failed_sources non-empty
  - `test_resync_updates_pipeline_run_id` — INSERT OR REPLACE semantics verified
