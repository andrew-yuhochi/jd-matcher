# Design Gate Review — jd-matcher PoC

> **Reviewer**: architect
> **Date**: 2026-04-24
> **Scope**: /poc-kickoff complete → /milestone-plan gate
> **Inputs reviewed**: `docs/poc/PRD.md`, `docs/poc/TDD.md`, `docs/poc/DATA-SOURCES.md`, `docs/poc/UX-SPEC.md`, `docs/poc/ALIGNMENT-LOG.md`, `docs/discovery/ROADMAP.md`

---

## Verdict: **PASS WITH NOTES**

All four gate documents exist, are non-trivial, internally consistent, and aligned to ROADMAP.md. No blocking issues. Two non-blocking notes are recorded for awareness during /milestone-plan.

---

## Per-check Results

| # | Check | Result | Evidence |
|---|-------|--------|----------|
| 1 | All four gate documents exist and are non-trivial | PASS | PRD.md (240 lines), TDD.md (418 lines, Part 1 complete with §1.0–§1.7), DATA-SOURCES.md (323 lines), UX-SPEC.md (403 lines). Each contains substantive PoC-specific content, not stubs. |
| 2 | TDD Part 1 data flow diagram complete | PASS | TDD §1.1 contains a Mermaid `flowchart LR` covering manual setup → Path A (Gmail-mediated closed platforms with Gmail Ingester → email parsers → JD Hydrator) and Path B (open APIs) → URL-seen check → LLM Extraction → Hard Filter → Embedding → Dedup → Storage → State check → Soft Rank → Web UI → events table → Analytics. CV branch is also rendered. The 13-step solution narrative in §1.0 mirrors the diagram. |
| 3 | PRD §4 references ROADMAP.md PoC exit criteria verbatim | PASS | PRD §4 (lines 75–82) reproduces ROADMAP.md §"Exit criteria (PoC)" (lines 64–70) word-for-word as a blockquote. Five-criterion list is byte-identical: components meet thresholds, end-to-end run on real data, hand-label sample counts (≥30/≥30/≥20), instrumentation captures one full session, PHASE-REVIEW.md produced and user-approved. |
| 4 | DATA-SOURCES.md covers every source in PRD Scope IN | PASS | PRD §5 names: LinkedIn (Gmail), Indeed (Gmail), JD hydration (LinkedIn + Indeed guest endpoints), Himalayas, Job Bank Canada (Gmail), Remotive, Jobicy, HN HNRSS. DATA-SOURCES.md has a per-source section for each (Path A: LinkedIn / Indeed / Job Bank; Path B: Himalayas / Remotive / Jobicy / HN; plus a dedicated "LinkedIn JD Hydration" section). No orphan sources on either side. |
| 5 | UX-SPEC milestone-aware and implementable | PASS | UX-SPEC §1 "Milestone-Aware UI Progression" gives M1/M2/M3/M4 end-state tables with concrete UI elements (tag chip slot, salary slot, CV chip slot, events written). §3 specifies CV settings layout with field types, max-length, save behaviour. §4 specifies analytics layout with concrete metrics + derivations. §5 enumerates concrete loading/error states with sub-bar copy. §6 locks the keyboard-shortcut scheme. Not abstract — implementer can build directly from this. |
| 6.1 | Cost figures consistent (LLM spend) | PASS | ROADMAP.md line 37: "Combined PoC LLM cost: ~$0.65/month at 20 postings/day". PRD §8 Constraints: "Combined ~$0.65/mo at 20 postings/day". PRD §5 M3 + ROADMAP M3 + TDD §1.3: extraction "~$0.60/mo at 20 postings/day", embeddings "~$0.04/mo". PRD SC-14: "≤$1/mo" budget envelope. All consistent. |
| 6.2 | Model choices consistent (gpt-4o-mini + text-embedding-3-small) | PASS | Cloud-default `gpt-4o-mini` for extraction + `text-embedding-3-small` for embeddings appears in: ROADMAP line 37 + M2 + M3, PRD §1 (Overview) + §5 M2 + M3 + §8 Constraints, TDD §1.0 + §1.3, DATA-SOURCES (Himalayas section + LinkedIn hydration ToS posture). Optional Ollama `qwen2.5:7b` + sentence-transformers `all-MiniLM-L6-v2` consistently named as config-swappable fallbacks. |
| 6.3 | Five commercial hedges reflected consistently | PASS | (1) Classify-always-filter-configurably: PRD §3 row 1 + §5 M3 + SC-15; TDD §1.0 step 8 + §1.1 diagram note + Part 2 row 11; UX-SPEC §1 M3 ("below-threshold postings simply absent from Main … stored in DB, hedge 1"). (2) Time-savings instrumentation: PRD §3 row 2 + §5 M1 + §5 M4 + SC-19; TDD §1.0 step 13 + §1.2 Events Recorder + §1.2a `events` table; UX-SPEC §1 M1 events row + §4 analytics page. (3) Namespace-aware schema: PRD §3 row 3 + §5 M1; TDD §1.2a (every table has `user_id`); UX-SPEC §4 ("All queries filter by `user_id = 'default'`"). (4) Taxonomy portability: PRD §3 row 4 + §5 M3; TDD §1.0 step 6 + §1.6 `classification.taxonomy`; UX-SPEC implicit (palette in §1 M3). (5) Open-source from day 1: PRD §3 row 5 + §5 M1; ROADMAP M1 AC #9; UX-SPEC not directly in scope. All five threaded coherently. |
| 6.4 | Scope OUT matches between PRD and DATA-SOURCES (deferred sources) | PASS | PRD §6 deferred-indefinitely list: Google for Jobs, Monster Canada, Wellfound/AngelList, aijobs.net, direct company career pages. DATA-SOURCES.md "Deferred sources (not in PoC)" table covers all five plus Greenhouse, Lever, Vancouver Tech Journal Jobs Board, BCtechjobs.ca with reasons. Greenhouse/Lever appear in both PRD §6 (deferred to MVP) and DATA-SOURCES (revisit at MVP-M2) — placement consistent. No orphan deferrals on either side. |
| 6.5 | M1–M4 milestone deliverables match across PRD §5, TDD §6, UX-SPEC §1 | PASS | M1 alignment: PRD §5 M1 (Gmail OAuth + LinkedIn/Indeed parsers + JD hydration + URL-dedup + applied/dismissed + FastAPI tabs + GitHub repo) ↔ TDD §6 components 1, 2, 3, 5, 10, 15, 18, 19 marked M1 ↔ UX-SPEC §1 M1 (three tabs, no tag chip, no CV chip, events written). M2 alignment: PRD (LLM normalisation + embeddings + dedup + Himalayas + repost) ↔ TDD §6 components 6 + 11 (M2 normalisation) + 13 + 14 ↔ UX-SPEC §1 M2 ("2 sources" badge, repost badge, canonical-keyed state). M3 alignment: PRD (full LLM extraction + hard filter + soft rank + taxonomy revision) ↔ TDD §6 components 11 (M3 full) + 12 + 16 ↔ UX-SPEC §1 M3 (primary tag chip, salary, soft-rank ordering, fit_score not shown). M4 alignment: PRD (CV recommender + Settings + Job Bank + Remotive + Jobicy + HN + analytics + coverage audit) ↔ TDD §6 components 4, 7, 8, 9, 17, 20 ↔ UX-SPEC §1 M4 (CV chip, settings, analytics nav). All four milestones consistent. |

---

## Notes (non-blocking)

1. **PRD §10 lists 8 open questions for milestone-plan resolution**. Expected and appropriate at this gate — these are the kinds of decisions that should be made at /milestone-plan with concrete data, not pre-decided in PRD. Items 1, 2, 4, 5 (LinkedIn keyword list, query specifics, dedup threshold, fit_threshold) explicitly carry default values in DISCOVERY-NOTES.md §10, so a milestone can proceed without a fresh user decision if the defaults are accepted. Open UX questions (item 7) → ux-designer at M1 milestone-plan; UX-SPEC §8 also lists 5 OQ items with documented defaults. No action required at this gate.

2. **ALIGNMENT-LOG.md flags one optional documentation enhancement** (Minor — optional severity): PRD §3 / §6 M3 does not explicitly link the optional M3 LLM benchmark sub-task to Beta Path B (free-local vs. paid-cloud tier) monetisation evaluation. Business-analyst's verdict was ALIGNED without correction; the suggestion was framed as "documentation gap, not a scope gap". Recommend the architect add a one-line note in PRD §6 M3 at the next /doc-update touch ("M3 benchmark results, if run, are input to Beta Path B evaluation"), but **not blocking** for /milestone-plan.

3. **TDD Part 2 is correctly deferred** to /milestone-plan per Gate 6 — §6 lists 20 components awaiting per-component spec entries (Input / Output / Responsibility / Quality Criteria / Pass Threshold / Sample Selection / Failure Handling). M1 milestone-plan must produce Part 2 entries for components 1, 2, 3, 5, 10, 15, 18, 19 before any TASKS.md entries can be written. This is expected behaviour, not a gap.

4. **`projects/jd-matcher/CLAUDE.md` requires update at /poc-kickoff close.** Currently shows Phase=Discovery (complete), Milestone=Not yet planned. Per portfolio Per-Project CLAUDE.md rules, /poc-kickoff is responsible for transitioning Phase=PoC and updating the document-paths block. Confirm this happens before /milestone-plan begins.

---

## Failures (blocking)

None.

---

## Corrections required

None blocking. The two optional enhancements above (commercial-tier link in PRD §3/§6 M3; CLAUDE.md phase-field update) can be addressed at /doc-update or as part of /milestone-plan housekeeping.

---

## Recommendation

**PROCEED to /milestone-plan jd-matcher** for M1. The design is internally consistent, traceable to ROADMAP.md exit criteria, and has measurable success criteria. M1 milestone-plan should:

1. Lock the LinkedIn keyword list (PRD §10 Q1 — accept the 7-keyword default unless user opts to add candidates).
2. Produce TDD Part 2 entries for the 8 M1 components (Gmail Ingester, LinkedIn parser, Indeed parser, JD Hydrator, URL-seen Check, State Manager [URL-keyed slice], Web UI [skeleton], Events Recorder).
3. Resolve UX OQ-3, OQ-4 from UX-SPEC §8 (single-column layout, `[Run sync now]` placement) before TASKS.md is written.
4. Update `projects/jd-matcher/CLAUDE.md` to Phase=PoC, Milestone=M1.
