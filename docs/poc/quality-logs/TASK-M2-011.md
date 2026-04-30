# TASK-M2-011 Quality Log

**Task**: Web UI updates (C8 + C9) — multi-source rendering + Reposted badge
**Date**: 2026-04-29
**Validator**: test-validator

---

## Unit tests

| Metric | Value |
|--------|-------|
| Total | 871 |
| Passed | 871 |
| Failed | 0 |
| Skipped | 10 (unchanged from pre-M2-011 baseline) |
| New tests added | 17 (tests/web/test_m2_ui.py) |

Baseline verified: 854 pre-existing tests + 17 new = 871 total. Math consistent.

Full suite ran in 27.35s via `.venv/bin/python -m pytest -v --tb=short`. Web-specific sub-suite (tests/web/): 135 tests, all passed.

---

## AC verification

| AC | Verdict | Evidence |
|----|---------|----------|
| AC1 multi-source rendering | PASS | `_card.html:47-55` — `Sources:` label + `{% for src in posting.sources %}` loop; `display_name` used for link text (`Apply on LinkedIn`, `Apply on Indeed`). Source precedence list hard-coded in `canonical_view.py:307-315` (`linkedin` → `indeed` → `himalayas` → …), applied in `_aggregate_link_info` at line 399. Tests `test_multi_source_card_shows_all_apply_links` and `test_multi_source_linkedin_before_indeed` both pass. |
| AC2 Reposted badge | PASS | `_card.html:27-36` — conditional on `posting.is_reposted`; `badge-reposted` CSS class; tooltip "This role was first seen on {date} and reposted under a new job ID". `canonical_view.py:389` sets `is_reposted = True` when `merge_kind == "repost"` in link rows. Tests `test_reposted_badge_renders_for_repost_canonical`, `test_reposted_badge_absent_for_non_repost`, `test_reposted_badge_has_tooltip` all pass. |
| AC3 canonical-level state | PASS | `routes.py:37` imports `select_main` from `canonical_view`; `canonical_view.py:194-207` — NOT EXISTS subqueries via `posting_canonical_links JOIN applied/dismissed` suppress the whole canonical when any linked posting is in either table. Tests `test_applying_one_posting_suppresses_whole_canonical` and `test_dismissing_one_posting_suppresses_whole_canonical` (both in test_m2_ui.py and mirrored in test_routes.py) pass. POST endpoints continue to take `posting_id` path param per TDD spec. |
| AC4 canonical-id keyboard handlers | PASS | `_card.html:14-17` — `id="card-{{ posting.canonical_id }}"` and `data-canonical-id="{{ posting.canonical_id }}"`. `app.js:389-406` — `o` handler uses `querySelector(".card-apply-link")` (first source URL, LinkedIn precedence via DOM order); `O` handler uses `querySelectorAll(".card-apply-link")` to open all source URLs. Tests `test_canonical_card_id_uses_canonical_id` and `test_canonical_card_has_data_posting_id` pass. |
| AC5 DOM tests | PASS | `tests/web/test_m2_ui.py` contains exactly 17 tests. All 17 pass. Tests cover: canonical-id as card DOM id, data-posting-id attr, single-source apply link, multi-source apply links, source precedence order, source-count badge present/absent, reposted badge present/absent/tooltip, apply-suppress, dismiss-suppress, O/o cheatsheet entries, .badge-reposted CSS, .badge-source-count CSS, failed-hydration no-filter extension. |
| AC6 no regression | PASS | 871 total pass, 0 fail. Pre-M2-011 baseline 854 + 17 new = 871. `seeded_db` fixture in `test_routes.py:40-118` correctly seeds 20 postings with matching canonical_postings + posting_canonical_links rows — accurately reflects M2 canonical-projection invariant (not a hack). `_insert_posting_with_canonical` helper at line 140-185 provides per-test canonical seeding for M2-specific assertions. |

---

## C8 deterministic invariants

| Invariant | Verdict | Evidence |
|-----------|---------|----------|
| (a) Each endpoint returns documented status code | PASS | `test_routes.py` — all 9 endpoints tested; GET `/`, `/applied`, `/dismissed`, `/healthz`, `/api/source-health` return 200; POST `apply/dismiss/restore/unapply` return 200; Pydantic 422 tested. |
| (b) Pydantic validation rejects malformed payloads (HTTP 422) | PASS | `test_apply_with_non_integer_id_returns_422`, `test_dismiss_with_non_integer_id_returns_422`, `test_restore_with_non_integer_id_returns_422`, `test_unapply_with_non_integer_id_returns_422` — all pass. |
| (c) Bind address is exactly 127.0.0.1 | PASS | `test_default_host_is_loopback` and `test_zero_zero_host_raises_value_error` pass. |
| (d) State-mutation endpoints are idempotent | PASS | `test_apply_idempotent`, `test_dismiss_idempotent`, `test_restore_idempotent_when_not_dismissed` all pass. |
| (e) Re-render after state mutation excludes posting from Main | PASS | `test_applied_posting_absent_from_main_tab`, `test_dismissed_posting_absent_from_main_tab` pass. |
| (f) Hydration-failure no-filter invariant | PASS | `test_main_view_shows_all_hydration_statuses` seeds 10 complete + 5 partial + 5 failed; asserts all 20 canonical card-ids in GET /. `test_main_view_includes_failed_hydration_postings` adds 3 explicit failed-hydration canonicals and asserts they appear. |
| (g) /api/source-health returns N entries | PASS | `test_source_health_returns_four_entries`, `test_source_health_never_run_when_no_rows` pass. |
| M2 extension: Main projects from canonical_postings; one card per canonical_id | PASS | `canonical_view.py:162-211` — SELECT from `canonical_postings` (not `postings`), NOT EXISTS via `posting_canonical_links`. `test_main_view_shows_all_hydration_statuses` asserts by canonical_id. |
| M2 extension: sources[] aggregated from postings_sources | PASS | `_aggregate_link_info` at `canonical_view.py:351-399` joins `posting_sources` per canonical link. `test_multi_source_card_shows_all_apply_links` (test_m2_ui.py) seeds 2 postings → 1 canonical with LinkedIn + Indeed sources, asserts both appear. |

Note: No test explicitly seeds 2 postings linked to 1 canonical and asserts GET / returns exactly ONE card with 2 entries in `sources[]`. The `test_multi_source_card_shows_all_apply_links` test asserts the two apply links appear in the single card fragment, which is sufficient to confirm the invariant. The `test_main_view_shows_all_hydration_statuses` test uses the seeded_db where each posting has its own canonical (1:1 mapping), so no test counts canonical-level card deduplication via a count assertion. This is a **Minor coverage gap** — not a code bug, but the C8 M2 invariant "one card per canonical_id when multiple postings link to same canonical" lacks a direct count-based test.

---

## C9 deterministic invariants

| Invariant | Verdict | Evidence |
|-----------|---------|----------|
| (a) DOM correctness via selectolax | PASS | Tests use FastAPI TestClient HTTP fetches + string/fragment assertions (same approach as selectolax pattern). `test_frontend_dom.py` passes 17 M1 DOM tests. |
| (b) Source-health badge invariants | PASS | `test_subbar_has_four_badges`, `test_badges_have_no_close_button`, `test_failed_badge_has_failure_reason_in_title` all pass (no regression). |
| (c) Hydration-indicator invariants | PASS | `test_hydration_failed_cards_present_in_main`, `test_failed_hydration_canonical_still_shows_warning` (M2 extension in test_m2_ui.py) — both pass. |
| M2 Reposted badge invariants | PASS | `badge-reposted` class present/absent correctly per merge_kind. Tooltip with title= attribute confirmed at `_card.html:31-34`. |
| M2 multi-source rendering | PASS | Sources row rendered in DOM with correct apply links and source precedence. |
| M2 source-count badge | PASS | `badge-source-count` present for >1 sources, absent for 1 source — both paths tested. |

---

## C9 subjective ergonomics

Defers to user demo at milestone close. Specifically:
- Reposted badge wording ("This role was first seen on YYYY-MM-DD" vs. TDD's "N days ago" phrasing) is in the subjective ergonomics bucket per TDD §C9 M2 update line 692 ("Subjective ergonomics for 'Reposted' badge wording, position, and color are flagged for user approval at M2 demo").
- Animation feel, keyboard responsiveness, and density are all user-approval gates.

---

## Issues found

**Minor — incomplete count-based canonical-projection test**
- `tests/web/test_routes.py` / `tests/web/test_m2_ui.py`
- The C8 M2 invariant "2 postings linked to 1 canonical → GET / returns 1 card with 2 sources[]" is covered by multi-source link rendering tests (which confirm both apply links appear in a single card fragment) but no test asserts `len(all_card_ids_in_html) == 1` when two postings share a canonical. The `seeded_db` fixture uses 1:1 posting-to-canonical mapping throughout. The `test_multi_source_card_shows_all_apply_links` test validates the multi-source rendering path correctly but does not assert that the two postings collapsed to a single canonical card.
- Classification: **Minor** (coverage gap, not a code bug — the logic is correct and exercised indirectly).

**Observation (not an issue) — tooltip wording**
- `src/jd_matcher/web/templates/_card.html:31-32`
- TDD §C9 line 692 uses "N days ago" as example phrasing; implementation uses "first seen on YYYY-MM-DD". Both convey the same information. Per TDD, badge wording is explicitly subjective — user decides at M2 demo. Not classified as a defect.

---

## Overall verdict: PASS WITH NOTES

All 871 tests pass. All 6 ACs are met. All 7 C8 deterministic invariants and all C9 deterministic invariants pass. One Minor coverage gap (no direct count assertion for 2-postings → 1-canonical deduplication in the main view) is non-blocking and may be addressed as part of TASK-M2-012 real-data validation if the developer chooses to add it. Subjective ergonomics (badge wording, animation feel) defer to user demo as designed.
