# Quality Log — TASK-M1-005 — Email URL parsers + URL-based dedup

**Date**: 2026-04-24
**Agent**: data-pipeline
**Gate**: Synthetic-fixture-first (Gate 4 §"Synthetic phase")

---

## AC Checklist

| AC | Status | Notes |
|----|--------|-------|
| LinkedIn parser: 100% URL extraction on 10 synthetic .eml fixtures | PASS | 28 URLs across 10 fixtures; 10/10 fixtures yield ≥1 posting |
| Indeed parser: 100% URL extraction on 10 synthetic .eml fixtures | PASS | 27 URLs across 10 fixtures; 10/10 fixtures yield ≥1 posting |
| URL regex: `linkedin.com/(?:comm/)?jobs/view/(\d+)` + Indeed `jk=` pattern | PASS | Both patterns tested including /comm/ variant and rt.indeed.com |
| raw_body persisted in posting_sources.raw_body | PASS | Stored as latin-1 string, round-trips to original bytes |
| seen_urls atomic insert (transactional) | PASS | `with conn:` context manager used; tested via dedup tests |
| Re-run produces 0 new postings | PASS | End-to-end: 28 new first pass, 0 new second pass |
| URL-only fallback: posting still inserted when title/company/location fail | PASS | Tested via test_url_only_fallback_still_inserts |

---

## Test Summary

| Test file | Tests | Passed | Failed |
|-----------|-------|--------|--------|
| tests/parse/test_linkedin_email.py | 13 | 13 | 0 |
| tests/parse/test_indeed_email.py | 13 | 13 | 0 |
| tests/dedup/test_url_dedup.py | 10 | 10 | 0 |
| **Prior tests (regression)** | 83 | 83 | 0 |
| **Total** | **119** | **119** | **0** |

---

## Demo Outputs

**LinkedIn fixture parse:**
```
SKIP_LIVE=1 python -m jd_matcher.parse --fixture linkedin/sample-001.eml
→ 3 ParsedPosting objects, canonical URLs: https://linkedin.com/jobs/view/999000{1,2,3}
```

**End-to-end re-run idempotency:**
```
First pass:  28 new postings (10 LinkedIn fixtures)
Second pass: 0 new postings (re-run idempotency PASS)
```

---

## Design Decisions / Deviations

1. **QP fallback strategy**: Some fixtures have `?jk=abc...` where QP decodes `=ab` as byte 0xAB (hex escape). Parser falls back to HTML when plain-text yields 0 URLs. This is consistent with real-world QP handling and ensures 100% extraction.

2. **`raw_body` stored as latin-1 string**: SQLite TEXT column; bytes encoded via `decode('latin-1')` which is a lossless bijection for all byte values. Caller can recover original bytes via `.encode('latin-1')`.

3. **Atomicity test approach**: `sqlite3.Connection.execute` is read-only in CPython, so the atomicity test was implemented by verifying the UNIQUE constraint on seen_urls prevents double-inserts, and that the `with conn:` pattern provides rollback semantics.

4. **Existing test updates**: `tests/ingest/test_gmail.py` updated to expect 10 fixtures per source (was 5) and relaxed MIME structure assertion to allow HTML-only fixtures (valid edge-case for parser fallback).

---

## Real-Data Validation

Deferred to TASK-M1-011 per Gate 4 sample-selection guidance. Real-data threshold: ≥95% URL extraction on ≥50 LinkedIn + ≥30 Indeed emails once user accumulates samples from dedicated Gmail account.

---

## Real-data sanity test added 2026-04-24

- Added `test_real_linkedin_email_parses` to `tests/parse/test_linkedin_email.py`
  to validate the parser against the real `.eml` user uploaded at
  `tests/fixtures/real/Altea Healthcare is hiring a data scientist.eml`.
- Test is parametrized over `tests/fixtures/real/*.eml` files matching
  LinkedIn sender — silently skipped on fresh checkouts (gitignored fixtures).
- Asserts ≥1 URL extracted per real email + canonical format valid.
- Result: 6 postings extracted from the real fixture — PASS.
- Total test count: 121 passed, 0 failed.

---

## Independent Validation Report (test-validator)
Date: 2026-04-24

| AC | Status | Evidence |
|----|--------|----------|
| AC1 LinkedIn parser 100% on 10 fixtures | PASS | All 10 parametrized tests pass; per-fixture counts verified (3,7,1,2,1,2,7,1,2,2 = 28 total); every fixture yields ≥1 posting |
| AC2 Indeed parser 100% on 10 fixtures | PASS | All 10 parametrized tests pass; per-fixture counts verified (3,2,6,2,1,2,5,1,2,3 = 27 total); every fixture yields ≥1 posting |
| AC3 URL regex variants both handled | PASS | LinkedIn regex `linkedin\.com/(?:comm/)?jobs/view/(\d+)` confirmed in linkedin_email.py:32; /comm/ variant tested in test_canonical_url_handles_comm_variant (PASS); Indeed regex `https?://(?:[a-z]+\.)?indeed\.com/[^\s"'<>]*?jk=([a-z0-9]+)` confirmed in indeed_email.py:37-40; rc/clk + rt.indeed.com variants pass |
| AC4 raw_body persisted | PASS | url_dedup.py:135 stores raw_body as latin-1 string in posting_sources.raw_body; test_register_new_stores_raw_body verifies round-trip (encode back to bytes matches original) |
| AC5 Best-effort field extraction | PASS | test_best_effort_title_extraction confirms title populated when HTML has link text; test_url_only_fallback_still_inserts confirms posting created even when all meta fields are None; no exceptions observed on any fixture |
| AC6 seen_urls atomic insert (transactional) | PASS | register_new uses `with conn:` (line 105) providing auto BEGIN/COMMIT/ROLLBACK; test_register_new_atomicity verifies UNIQUE constraint prevents double-insert within the transaction |
| AC7 Re-run produces 0 new postings | PASS | test_re_run_pipeline_produces_zero_new_postings: 10 'new' on first pass, 10 'seen' on second pass; DB state: exactly 10 postings, 10 seen_urls rows |
| AC8 URL-only fallback | PASS | test_url_only_fallback_still_inserts uses sample-010 (HTML-only with minimal structure); postings returned with URL populated even when title/company/location are None; register_new succeeds with all-None meta fields (confirmed by test_register_new_inserts_posting_and_returns_new with title/company/location present, and parser logic always returns posting when URL found) |

Real-data sanity test: PASS — 6 postings extracted from "Altea Healthcare is hiring a data scientist.eml"; all pass canonical format validation (https://linkedin.com/jobs/view/{digits}); 1 real fixture file found; test runs (not skipped)

Structural sanity:
- 20 fixtures parseable MIME: PASS — 10 LinkedIn + 10 Indeed fixtures all pass test_linkedin_fixtures_have_required_mime_structure and test_indeed_fixtures_have_required_mime_structure (from test_gmail.py); sample-010 (LinkedIn) and sample-009 (Indeed) are HTML-only (text/html Content-Type only) not multipart/alternative; parsers handle both structures
- beautifulsoup4 pinned: PASS — requirements.txt line 7: beautifulsoup4==4.13.5
- ParsedPosting fields: PASS WITH NOTE — dataclass at linkedin_email.py:35-48 has source, url, raw_url, job_id, title, company, location, received_at, raw_body; TDD §C4 Output spec lists apply_url and raw_email_body as field names, but TASKS.md ACs use raw_body (schema name); apply_url absent from ParsedPosting (Minor — dead field not yet needed in M1; no AC requires it)
- URL canonicalization: PASS — LinkedIn produces https://linkedin.com/jobs/view/{id} (no query params, no /comm/); test_canonical_url_strips_tracking_params and test_canonical_url_format both pass; NOTE: _canonicalize_url() at linkedin_email.py:225 is defined but never called (dead code — canonicalization done inline); Minor issue
- Within-email dedup: PASS — test_within_email_dedup for both LinkedIn (sample-008: 2 occurrences → 1 posting for job_id 6660081) and Indeed (sample-008: 2 occurrences → 1 posting for job_id dup0001234567001)
- HTML-only fallback: PASS — test_html_only_body_falls_back_to_html for LinkedIn (sample-010: job_ids 4440101, 4440102 extracted) and Indeed (sample-009: job_ids html9001234567001, html9001234567002 extracted)

Issues found:
- [Minor] linkedin_email.py:225 — `_canonicalize_url()` is defined but never called; dead code. Canonicalization is performed inline in _parse() via f-string. No behavioral impact.
- [Minor] TDD §C4 Output field names do not match implementation: TDD lists `apply_url` (absent from ParsedPosting) and `raw_email_body` (implemented as `raw_body`). TASKS.md ACs use `raw_body` (the schema name), so TASKS.md ACs are satisfied. Recommend aligning TDD field names to match implementation, or implementing `apply_url` stub.

Unit tests: 121 passed, 0 failed (required: 100%) — PASS
Overall verdict: PASS
