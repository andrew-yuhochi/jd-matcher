# Quality Log — TASK-M2-015: Collapsed-card layout reshuffle + skills always visible

**Date**: 2026-04-29  
**Evaluator**: data-pipeline agent

---

## Test Results

| Suite | Before | After | Delta |
|-------|--------|-------|-------|
| Full suite (pass) | 886 | 893 | +7 new tests |
| Full suite (skip) | 10 | 10 | 0 |
| Full suite (fail) | 0 | 0 | 0 |
| `test_m2_ui.py` | 30 | 39 | +9 (7 new, 2 updated) |

All 893 tests pass, 10 skipped (live tests gated by SKIP_LIVE).

---

## Layout Changes Validated

### Before (M2-014 layout)
- Line 1: `title` | `#id chip` | `seniority chip` | `Company` | `variants badge` | `Reposted badge`
- Line 2: `location · sources (apply links)` (inline)
- Line 3 (conditional): `team_or_department` (separate div)
- Line 4 (conditional): `role_summary teaser`
- Line 5: `First seen: date`
- Expanded: skills strip + JD body

### After (M2-015 layout — 5 lines)
- Line 1: `Title — Company` (left flex) | right cluster: `variants`, `Reposted`, `seniority chip`, `#id chip`
- Line 2 (`.card-line2-meta`): `Location · Team` (dot-separated, null-safe; absent when both null)
- Line 3 (`.card-skills-strip`): skills chip strip always in collapsed view (up to 10 chips; absent when empty)
- Line 4 (`.card-role-summary-teaser`): first-sentence teaser ~120 chars
- Line 5 (`.card-line5-footer`): `Sources: [Apply links]` (left) | `First seen: date` (right)
- Expanded: JD body only (skills strip removed)

---

## Sample DOM — Merged Canonical (canonical_id 312, Coalition)

```
id="card-312" data-posting-id="10" data-canonical-id="312"

Line 1:  "Applied Scientist II — Coalition" | [2 variants] [Mid] [#312]
Line 2:  "Toronto"
Line 3:  [Machine Learning] [Generative AI] [Python] [SQL] [Statistical Analysis]
         [Data Analysis] [Data Engineering] [Deep Learning] [MLOps] [A/B Testing]
Line 4:  "The Applied Scientist II will build and improve machine learning and Generative AI models…"
Line 5:  "Sources: Apply on LinkedIn  Apply on LinkedIn" | "First seen: 2026-04-28"
```

Merged canonical correctly shows:
- `2 variants` badge in right cluster
- Two "Apply on LinkedIn" links (one per merged posting_id)
- Skills strip visible in collapsed view (10 chips — full cap)
- No Reposted badge (merge_kind = content_dedup, not repost)

---

## Sample DOM — Non-Merged Canonical (canonical_id 457, Work Consulting)

```
id="card-457" data-posting-id="98" data-canonical-id="457"

Line 1:  "Research And Development Specialist (Project-Based Collaboration) — Work Consulting" | [Mid] [#457]
Line 2:  "Remote — Canada"
Line 3:  [AI] [Computer Science] [Biomedical Science] [Physics] [Chemistry]
         [Materials Science] [Automation] [Drones] [Autonomous Systems] [Experimental Design]
Line 4:  "The role involves driving research and development projects across various scientific…"
Line 5:  "Sources: Apply on LinkedIn" | "First seen: 2026-04-28"
```

Single-source canonical correctly shows:
- No variants badge
- No Reposted badge
- Single "Apply on LinkedIn" link
- Skills strip visible in collapsed view (10 chips — full cap)

---

## Null-Safety Validation

Metadata row null-safety was tested by all 4 new `test_metadata_row_*` tests:

| Scenario | Expected | Result |
|----------|----------|--------|
| location + team both present | `Location · Team` | PASS |
| team null (location only) | `Location` (no dot) | PASS |
| location null (team only) | `Team` (no dot) | PASS |
| both null/empty | row absent | PASS |

No stray `· ·` or leading/trailing dots observed in any scenario.

---

## Files Modified

- `src/jd_matcher/web/templates/_card.html` — 5-line collapsed layout
- `src/jd_matcher/web/templates/_card_jd_body.html` — skills strip removed
- `src/jd_matcher/web/static/css/styles.css` — `.card-line1` flexbox refactor, new `.card-line2-meta`, `.card-line5-footer`, `.card-line1-right`, `.card-title-company`
- `tests/web/test_m2_ui.py` — 2 tests updated, 9 new tests added (39 total in file)
- `docs/poc/TDD.md` — §C9 M2-015 update note appended
