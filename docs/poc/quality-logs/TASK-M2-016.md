# Quality Log — TASK-M2-016: Skills Tiering

**Date**: 2026-04-29
**Agent**: data-pipeline
**Component**: C9 (Web UI: frontend) — skills strip

---

## Test Results

| | Count |
|---|---|
| Baseline (pre-task) | 893 passed, 10 skipped |
| New tests added | 12 |
| Final result | **905 passed, 10 skipped, 0 failed** |
| Regressions | 0 |

All 12 new tests:
- `test_classify_and_sort_skills_returns_correct_counts` — PASSED
- `test_alias_matching_genai_matches_generative_ai` — PASSED
- `test_alias_matching_case_insensitive` — PASSED
- `test_skills_ordered_ds_then_lang_then_platform_then_other` — PASSED
- `test_empty_user_profile_all_skills_render_as_nomatch` — PASSED
- `test_skills_capped_at_10_after_sorting` — PASSED
- `test_unknown_skill_falls_back_to_other_category` — PASSED
- `test_match_skill_renders_with_category_color` — PASSED
- `test_nonmatch_skill_renders_gray` — PASSED
- `test_skills_match_count_footer_renders` — PASSED
- `test_skills_match_count_zero_total_no_footer` — PASSED
- `test_m2016_css_rules_exist` — PASSED

---

## Live DB Sample — Canonical 312 (Coalition, Applied Scientist II)

Skills: ["Machine Learning", "Generative AI", "Python", "SQL", "Statistical Analysis", "Data Analysis", "Data Engineering", "Deep Learning", "MLOps", "A/B Testing"]

```
Skills match: 9/10
  ✓ [ds_ml      ] Machine Learning    → purple chip
  ✓ [ds_ml      ] Generative AI       → purple chip
  ✓ [ds_ml      ] Statistical Analysis→ purple chip
  ✓ [ds_ml      ] Data Analysis       → purple chip
  ✓ [ds_ml      ] Deep Learning       → purple chip
  ✓ [ds_ml      ] MLOps               → purple chip
  ✓ [ds_ml      ] A/B Testing         → purple chip
  ✓ [languages  ] Python              → blue chip
  ✓ [languages  ] SQL                 → blue chip
  · [other      ] Data Engineering    → gray chip
```

9/10 matches. Ordering: all DS/ML matches grouped first, then Languages (Python, SQL), then the one non-match (Data Engineering, other-category) at the end. Correct.

---

## Live DB Sample — Canonical 377 (Lumenalta, AI Engineer) — match-light context

Skills: ["Python", "TensorFlow", "PyTorch", "Scikit-Learn", "Spark", "Airflow", "Kafka", "n8n", "LangGraph", "Machine Learning"]

```
Skills match: 6/10
  ✓ [ds_ml      ] Machine Learning    → purple chip
  ✓ [languages  ] Python              → blue chip
  ✓ [platforms  ] TensorFlow          → green chip
  ✓ [platforms  ] PyTorch             → green chip
  ✓ [platforms  ] Scikit-Learn        → green chip
  ✓ [platforms  ] Spark               → green chip
  · [platforms  ] Airflow             → gray chip
  · [platforms  ] Kafka               → gray chip
  · [platforms  ] n8n                 → gray chip
  · [platforms  ] LangGraph           → gray chip
```

6/10 matches. Ordering: match priority correct (ds_ml first, then languages, then platforms). Non-matching platforms (Airflow, Kafka, n8n, LangGraph) rendered in original input order at the end.

---

## Live DB Alias Validation

| Card skill | User profile entry | Match? |
|---|---|---|
| GenAI | Generative AI | Yes (alias) |
| scikit-learn | Scikit-Learn | Yes (alias + lowercase) |
| python | Python | Yes (case-insensitive) |

---

## Notes

- `Data Engineering` does not match any core_skill and has no category assignment in ds_ml/languages/platforms — falls to `other` (gray). This is correct: the user's profile focuses on analytical/ML skills, not data engineering infrastructure.
- `Snowflake` is in the platforms category but not in user's core_skills — renders as `skill-chip-platform skill-chip-nomatch` (gray, correct).
- Footer placement: placed between the chip strip (line 3) and the role summary teaser (line 4). This feels right visually — it's a one-line label immediately below the chips it describes, and keeps the role summary clearly separated below it.
- The `Skills match: X/Y` footer is small, italic, muted (`.card-skills-footer`). It functions as a quick at-a-glance signal without dominating the card layout.
