# Quality Log — TASK-M1-002
# SETUP.md + saved-search keyword discussion

**Date**: 2026-04-24
**Agent**: content-writer
**Status**: Done (2026-04-24)

---

## AC Checklist

| # | Acceptance Criterion | Status | Notes |
|---|---------------------|--------|-------|
| AC1 | `docs/poc/SETUP.md` exists with 10 numbered steps covering: dedicated Gmail confirmation, GCP project + Gmail API enabled, OAuth client (Desktop type) downloaded, OpenAI API key configured in `.env`, LinkedIn saved searches set up (per agreed list), Indeed saved searches set up, Job Bank Canada alerts (deferred to M4 — noted), 5 CV variants in local folder (deferred to M4 — noted), `python -m jd_matcher.auth` first-run authorization, sanity-check pipeline run | PASS | All 10 steps present. Steps 7 and 8 explicitly noted as deferred to M4. |
| AC2 | `config/saved-searches.yaml` captures the final user-approved keyword list (≥7 entries) + location filters per platform | PASS | 10 terms captured (exceeds ≥7 minimum). Two locations per platform documented with platform-specific filter syntax. Sender filters included. `total_saved_searches: 40`. |
| AC3 | User has confirmed they have set up the alerts on LinkedIn + Indeed (subjective — user signs off on followability) | PENDING USER SIGNOFF | SETUP.md is complete and followable. User must perform the 40-search setup and confirm. This AC cannot be passed by content-writer. |
| AC4 | SETUP.md cross-references DATA-SOURCES.md sections for each step | PASS | Cross-reference table at bottom of SETUP.md maps every step to DATA-SOURCES.md section + TASK-ID. Inline references in steps 5 and 6 also point to specific DATA-SOURCES.md sections. |

---

## Final keyword list (user-approved 2026-04-24)

10 terms, standardized across LinkedIn and Indeed:

1. Data Scientist
2. Senior Data Scientist
3. Machine Learning Engineer
4. Applied Scientist
5. Data Science
6. Research Scientist
7. Senior Data Analyst
8. AI Engineer
9. Applied AI Research
10. Quant Research

Removals from original DISCOVERY-NOTES.md §4 seed list: `Staff Data Scientist` (above stated seniority band).
Additions confirmed by user: `Senior Data Analyst`, `AI Engineer`, `Applied AI Research`, `Quant Research`.

---

## Final location strategy

Split-location design (user-approved 2026-04-24):

- Each term gets two separate saved searches per platform: one for Vancouver, BC specifically; one for Canada (Remote) specifically.
- Rationale: combining both in one search dilutes Vancouver-specific recall; splitting forces each location to surface its strongest matches independently; the dedup layer collapses overlap.
- Result: 10 terms × 2 locations × 2 platforms = **40 saved searches total**.

---

## Files produced

| File | Path | Status |
|------|------|--------|
| SETUP.md (updated) | `projects/jd-matcher/docs/poc/SETUP.md` | Complete |
| saved-searches.yaml (new) | `projects/jd-matcher/config/saved-searches.yaml` | Complete |

---

## Pending action (AC3)

Task cannot be marked Done until the user confirms:
- 20 LinkedIn saved searches created (10 terms × Vancouver-BC + Canada-Remote)
- 20 Indeed saved searches created (10 terms × Vancouver-BC + Canada-Remote)

Once user confirms, orchestrator updates status to `Done (YYYY-MM-DD)` and Progress Summary to `Done: 2`.

---

## Independent Validation Report (test-validator)
Date: 2026-04-24

| AC | Status | Evidence |
|----|--------|----------|
| AC1 | PASS | File exists at `docs/poc/SETUP.md`. 10 distinct numbered step headings verified (steps 1–10). All required topics present: dedicated Gmail (step 1), GCP + Gmail API (step 2), OAuth Desktop client (step 3), `.env` + OpenAI key (step 4), LinkedIn saved searches (step 5), Indeed saved searches (step 6), Job Bank Canada (step 7 — marked "DEFERRED TO M4"), CV variants (step 8 — marked "DEFERRED TO M4"), `python -m jd_matcher.auth` (step 9), sanity-check pipeline run (step 10). Both deferred steps carry explicit "DEFERRED TO M4" heading text. |
| AC2 | PASS | YAML parses without error. `terms` list contains exactly 10 entries matching the user-approved list in full (Data Scientist, Senior Data Scientist, Machine Learning Engineer, Applied Scientist, Data Science, Research Scientist, Senior Data Analyst, AI Engineer, Applied AI Research, Quant Research). Location filters documented for both platforms (`vancouver-bc`: LinkedIn="Vancouver, British Columbia, Canada", Indeed="Vancouver, BC"; `canada-remote`: LinkedIn="Canada (with On-site/Remote = Remote)", Indeed="Canada (with Remote toggle = on)"). Sender filters present for both platforms. `total_saved_searches: 40` confirmed. Note: terms are in a shared top-level list rather than duplicated per-platform — both platforms reference the same 10 terms via `saved_search_count: 20` each; this satisfies the "≥7 for LinkedIn + ≥2 for Indeed" requirement. |
| AC3 | PENDING (user signoff required) | — |
| AC4 | PASS | Cross-reference table at end of SETUP.md maps all 10 steps to DATA-SOURCES.md sections. 4 spot-checks against actual DATA-SOURCES.md content: step 1 → `§Gmail (transport)` (line 28 heading confirmed), step 5 → `§LinkedIn (via Gmail alerts)` (line 52 heading confirmed), step 6 → `§Indeed.ca (via Gmail alerts)` (line 79 heading confirmed), step 10 → `§"Manual setup checklist" step 10` (line 296 section + step 10 confirmed). All 4 cross-references resolve to real sections. Inline references within steps 1, 2, 3, 5, 6 also point to specific DATA-SOURCES.md sections. |

Unit tests: 0 collected, 0 failed (no tests exist yet — skeleton stage; exit code 5 treated as PASS per project convention)

Minor issue — PyYAML not in `requirements.txt`: The venv does not include `pyyaml`. YAML validation required temporary installation. If `config/saved-searches.yaml` is to be programmatically read in future tasks, `pyyaml` must be added to `requirements.txt`. Classify: **Minor** (missing dependency declaration).

Overall verdict: PASS WITH NOTES (AC3 pending user signoff; Minor: pyyaml missing from requirements.txt)

---

## AC3 Sign-off — 2026-04-24

**User confirmed**: All 40 saved searches are live (LinkedIn 20 + Indeed 20). AC3 met.

**Actual allocation that emerged through interactive design:**

LinkedIn (20 alerts, 20-alert cap):
- `Data Scientist` split across 3 experience levels (Entry / Senior / Manager) × 2 locations = 6 alerts. Rationale: closest-fit term; split-by-level captures misclassified-as-Entry postings and maximizes email-digest exposure across all seniority bands.
- 7 other terms × 1 combined-level alert × 2 locations = 14 alerts.
- Locations: `Greater Vancouver Metropolitan Area` (NOT "Vancouver, BC" — broader catchment) and `Canada (Remote)`.
- Dropped from LinkedIn due to cap: `Senior Data Scientist` (redundant with split-by-level filter); `Applied AI Research` (overlap with Applied Scientist + Research Scientist union).

Indeed (20 alerts, no experience filter):
- 10 terms × 2 locations = 20 alerts. No experience filter applied — Indeed's filter is unreliable; seniority triage handled by keyword prefix + pipeline seniority hard-filter (M2).
- Terms include `Senior Data Scientist` and `Applied AI Research` (retained here because title-prefix targeting substitutes for filter, and Indeed's 10-term list fills the 20-alert cap cleanly).
- Locations: `Vancouver, BC` and `Canada (Remote toggle ON)`.

`saved-searches.yaml` updated to version 1.1 reflecting this actual allocation. `SETUP.md` steps 5 and 6 updated to match.

**Final AC table:**

| # | Acceptance Criterion | Status |
|---|---------------------|--------|
| AC1 | SETUP.md exists with 10 steps | PASS |
| AC2 | saved-searches.yaml with ≥7 LinkedIn + ≥2 Indeed entries | PASS |
| AC3 | User confirmed 40 alerts live on LinkedIn + Indeed | PASS (user sign-off 2026-04-24) |
| AC4 | SETUP.md cross-references DATA-SOURCES.md | PASS |
