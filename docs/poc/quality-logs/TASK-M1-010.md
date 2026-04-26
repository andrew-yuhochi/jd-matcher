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

## Tag chip / salary / CV chip — NOT rendered at M1

Confirmed absent from `_card.html`. The template renders exactly:
- Line 1: title — company (bold) + optional ⚠ warning
- Line 2: location · Apply link (if URL present)
- Line 3: First seen date
- Action buttons (hidden by default)
- Expanded body (hidden until `e` pressed)

No tag chips, salary fields, or CV chips rendered. Per TDD §C9 and UX-SPEC §1 explicit absence.
