# Quality Log — TASK-M2-003 — Title-Based Interest Filter (C19)

**Date**: 2026-04-27
**Agent**: data-pipeline
**Component**: C19 (Title-Based Interest Filter)

---

## Acceptance Criteria Verdicts

| AC | Description | Verdict |
|----|-------------|---------|
| AC1 | `config/title_filters.yaml` with deny_patterns (Director/VP/Head of/Chief/SWE without ML/BI/QA/DevOps/Frontend/Backend) and allow_patterns (ML/Data escape hatches) | PASS |
| AC2 | `filter_title()` returns `FilterDecision {action, matched_pattern, reason}` | PASS |
| AC3 | Filter applied between C4 and C6 in pipeline; `email_ingest_log.filter_status='filtered'` and `filter_reason` set | PASS |
| AC4 | Filtered postings NEVER reach hydration, LLM extraction, embedding, or dedup | PASS |
| AC5 | 100% on synthetic test fixtures (20 deny / 20 pass / 10 ambiguous) | PASS — 50/50 |
| AC6 | No live network calls in test path | PASS |

---

## Pytest Summary

```
521 passed, 1 skipped, 31 warnings in 6.33s
```

New tests added: 68 (7 integration + 61 unit/edge).

Previous baseline: 453 passed, 1 skipped.
New total: 521 passed, 1 skipped — no regressions.

---

## Synthetic Fixture Results (AC5)

**50/50 PASS** across all three categories:

| Category | Count | Result |
|----------|-------|--------|
| Should-DROP titles | 20 | 20/20 PASS |
| Should-PASS titles | 20 | 20/20 PASS |
| Ambiguous (deny + allow; allow wins) | 10 | 10/10 PASS |
| Edge cases (empty, non-English, HTML entities, substring, shape) | 18 | 18/18 PASS |

Total: 68/68 PASS.

Sample deny cases (verified DROP):
- "Director of Engineering" → DROP (matched: `\bDirector\b`)
- "VP of Engineering" → DROP (matched: `\bVP\b`)
- "Software Engineer" → DROP (matched: `\bSoftware (Engineer|Developer)\b`)
- "DevOps Engineer" → DROP (matched: `\bDevOps (Engineer|Developer|Specialist)\b`)
- "Business Intelligence Analyst" → DROP (matched: `\bBusiness Intelligence (Analyst|Developer|Specialist|Manager|Engineer)\b`)

Sample pass cases (verified PASS):
- "Senior Data Scientist" → PASS
- "MLOps Engineer" → PASS
- "Staff Machine Learning Engineer" → PASS
- "Analytics Engineer" → PASS

Sample ambiguous cases (deny matches, allow overrides → PASS):
- "Director of Data Science" → PASS (allow override: Director.*Data Science)
- "VP of Machine Learning" → PASS (allow override: VP.*Machine Learning)
- "Software Engineer (ML)" → PASS (allow override: Software Engineer.*ML)
- "Backend Engineer, Data Platform" → PASS (allow override: Backend Engineer.*Data Platform)
- "DevOps Engineer (ML Infrastructure)" → PASS (allow override: DevOps Engineer.*ML)

---

## Demo CLI Outputs (Demo Artifact)

```
$ .venv/bin/python -m jd_matcher.filter.title_filter --title "Director of Engineering"
DROP — matched pattern: \bDirector\b — reason: Block Director-level unless allow override matches

$ .venv/bin/python -m jd_matcher.filter.title_filter --title "Senior Data Scientist"
PASS

$ .venv/bin/python -m jd_matcher.filter.title_filter --title "Director of Data Science"
PASS — allow override matched: Director.*(Data Science|Machine Learning|Artificial Intelligence|AI|Analytics|Data Engineering|Data Platform|Data)
```

---

## filter_status Semantics Decision (Option C)

**Decision**: `email_ingest_log.filter_status='filtered'` is set ONLY when ALL postings extracted from an email were dropped by C19 (Option C). Partial-filter cases — where some postings passed and some were dropped — leave `filter_status` as NULL.

**Rationale**: The per-email `filter_status` column is intended for the future Filtered Tab UI to show "entirely-filtered emails" as a distinct category. Partial-filter emails are captured at the run level via `SourceResult.filtered_count` (rolled into the `gmail_source_step` log event as `filtered_by_title`).

**Invariant tested**: Integration test `TestMixedEmail::test_email_log_filter_status_null_for_partial_filter` confirms NULL for partial; `TestAllFilteredEmail::test_filter_status_set_to_filtered` confirms 'filtered' for all-dropped.

---

## Pipeline Integration Verified

- Filtered postings short-circuit BEFORE `register_new` → no `seen_urls` write.
- No hydration call for filtered URLs (verified by `TestNoHydrationForFiltered`).
- `SourceResult.filtered_count` populated correctly.
- `gmail_source_step` log event includes `filtered_by_title` count.
- `mark_filtered()` writer added to `email_ingest_log.py`.

---

## Real-Data Calibration

Deferred to TASK-M2-004 per TDD §C19. The calibration task will:
1. Run C19 against the existing 91 PoC postings.
2. Generate a validation report (`python -m jd_matcher.report ingest --filtered`).
3. User reviews filtered list; adjusts `config/title_filters.yaml` until precision ≥95% and recall ≥98%.

The probabilistic quality threshold (Gate 4) will be evaluated and approved by the user in TASK-M2-004 before the M2 milestone closes.

---

## Files Created / Modified

| File | Action |
|------|--------|
| `src/jd_matcher/filter/__init__.py` | Created (package marker) |
| `src/jd_matcher/filter/title_filter.py` | Created (FilterDecision, TitleFilters, load_filters, filter_title, CLI) |
| `config/title_filters.yaml` | Created (seed deny + allow patterns, ~45 rules) |
| `src/jd_matcher/db/email_ingest_log.py` | Modified (added mark_filtered writer) |
| `src/jd_matcher/pipeline.py` | Modified (C19 integration, SourceResult.filtered_count, gmail_source_step log) |
| `tests/filter/__init__.py` | Created |
| `tests/filter/test_title_filter.py` | Created (61 test cases) |
| `tests/filter/test_pipeline_integration.py` | Created (7 integration tests) |
| `docs/poc/TASKS.md` | Updated (TASK-M2-003 Done, progress counts) |
| `docs/poc/quality-logs/TASK-M2-003.md` | Created (this file) |
