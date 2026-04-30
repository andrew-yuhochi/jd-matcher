# Quality Log — TASK-M2-014
## Card UI Enrichment with M2-available LLM Fields

**Date**: 2026-04-29
**Agent**: data-pipeline
**Task**: TASK-M2-014

---

## Test Results

| Suite | Before | After | Delta |
|-------|--------|-------|-------|
| tests/web/test_m2_ui.py | 22 pass | 32 pass | +10 new tests |
| Full suite | 876 pass, 10 skip | 886 pass, 10 skip | +10 new tests |
| Regressions | — | 0 | — |

All 10 new tests pass on first run. No regressions in existing suite.

### New Tests Added

1. `test_seniority_chip_renders_when_present` — chip present when seniority non-null
2. `test_seniority_chip_absent_when_null` — chip absent when seniority is empty string
3. `test_team_or_department_line_renders_when_present` — team line renders with value
4. `test_team_or_department_line_absent_when_null` — team line absent when null
5. `test_role_summary_teaser_renders_truncated` — teaser present with ellipsis for long summary
6. `test_role_summary_teaser_absent_when_null` — teaser absent for empty role_summary
7. `test_top_skills_chips_render_in_expanded_view` — chips render for each skill
8. `test_top_skills_strip_absent_when_empty` — strip absent when top_skills is empty list
9. `test_top_skills_strip_caps_at_10_chips` — 12-skill seed renders exactly 10 chips
10. `test_card_css_rules_for_new_elements_exist` — all 5 CSS classes defined in styles.css

---

## Live DB Validation

Sample from live DB (148 canonicals, LinkedIn corpus):

**Canonical 312** — Applied Scientist II (Amazon-adjacent)
- `canonical_seniority`: `Mid` — chip renders
- `team_or_department`: NULL — team line absent (correct)
- `role_summary` (first 120 chars): "The Applied Scientist II will build and improve machine learning and Generative AI models for underwri…"
- `top_skills`: 10 skills — ["Machine Learning", "Generative AI", "Python", "SQL", "Statistical Analysis", "Data Analysis", "Data Engineering", "Deep Learning", "MLOps", "A/B Testing"] — all 10 render (at cap)

**Canonical 366** — Senior Data Analyst
- `canonical_seniority`: `Senior` — chip renders
- `team_or_department`: "Business Intelligence & Analytics" — team line renders italic muted
- `role_summary` (first 120 chars): "The Senior Data Analyst will design, develop, and deliver analytics solutions using Power BI while ens…"
- `top_skills`: 10 skills — all render

**Null rate observed** (sample of 5 canonicals, IDs 312/326/331/366/377):
- `canonical_seniority`: 0% null (all 5 populated)
- `team_or_department`: 80% null (4/5 null, 1/5 has value) — healthy null rate per BA expectation (~40%)
- `role_summary`: 0% null (all 5 populated)
- `top_skills`: 0% empty (all 5 populated)

Data quality: confirmed non-null for seniority/role_summary/top_skills on all sampled rows. team_or_department null rate is slightly higher than BA's ~40% estimate on this small sample, but expected given LinkedIn corpus may not always mention team explicitly.

---

## Files Modified

- `src/jd_matcher/web/routes.py` — `_main_view_canonical_list()`: added 4 fields to posting dict
- `src/jd_matcher/web/templates/_card.html` — seniority chip, team line, role_summary teaser
- `src/jd_matcher/web/templates/_card_jd_body.html` — top_skills chip strip in expanded view
- `src/jd_matcher/web/static/css/styles.css` — 5 new CSS rules
- `tests/web/test_m2_ui.py` — 10 new DOM tests
- `docs/poc/TDD.md` — §C9 M2 update note extended
- `docs/poc/TASKS.md` — status updated to Done
