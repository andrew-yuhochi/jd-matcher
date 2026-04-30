# Alignment Log — jd-matcher — PoC

> Logged by business-analyst for every new requirement raised in conversation and milestone reviews.
> Each entry captures a proposal, BA verdict, user decision, and where the requirement went.

---

## 2026-04-24 — Mode A: PRD §3 Commercial Thesis vs. MARKET-ANALYSIS.md — PoC kickoff alignment check

- **Triggered by**: /poc-kickoff (PRD drafting step)
- **Mode**: A
- **Documents compared**:
  - `projects/jd-matcher/docs/poc/PRD.md` — §3 Commercial Thesis (Agreed), §6 Scope IN, §7 Scope OUT
  - `projects/jd-matcher/docs/discovery/MARKET-ANALYSIS.md` — Commercial Verdict, Beta-Transition Decision Framework, Strategic Recommendations, Commercial Risks

---

### Verdict: ALIGNED

The PRD §3 Commercial Thesis faithfully reflects the MARKET-ANALYSIS.md commercial thesis in every substantive claim. No corrections are required before locking the PRD.

---

### Alignment Findings — Claim-by-Claim

| Claim in PRD §3 | Source in MARKET-ANALYSIS.md | Match? |
|---|---|---|
| "Personal-first throughout PoC and MVP" | "For PoC/MVP, the personal-first framing is unambiguously correct: urgency is high, the market is the author" (Executive Summary) | PASS |
| "commercial viability is 'Low-to-Medium, conditional on Beta gate validation'" | "Viability: Low-to-Medium — conditional on Beta gate validation." (Commercial Verdict) | PASS — verbatim |
| "the niche of 'Vancouver DS/ML + OWP' is too small to anchor a commercial product" | "A commercial TAM for 'Canadian DS/ML job seekers with immigration constraints' is in the thousands — too small for a standalone commercial venture." (Market Size & Segments) | PASS |
| "any commercial path requires generalising the tool to senior technical job seekers globally with cross-source aggregation pain" | "Expanding further to 'all senior technical job seekers globally facing cross-source aggregation noise' is a plausible TAM but requires stripping Canadian-specific logic" (Market Size & Segments); Strategic Recommendation 1 confirms this as the commercial wedge | PASS |
| Five hedges from DISCOVERY-NOTES.md §10.5 listed in table | All five hedges are consistent with MARKET-ANALYSIS.md's PoC/MVP Implications and Strategic Recommendations (namespace-awareness in Recommendation 4; time-savings instrumentation in Recommendation 3; open-source in Recommendation 2; taxonomy portability in Recommendation 1) | PASS |
| "Deferred to pre-Beta: hand-labeled benchmark extension from 30 → 100 postings" | Consistent with Commercial Verdict: "Recommended positioning: Personal-first through MVP; at Beta, evaluate commercial viability against the three concrete gates" — pre-Beta is the correct placement | PASS |
| LinkedIn ToS "acknowledged commercial wall" — "HiQ Labs precedent — MARKET-ANALYSIS.md Risk 1" | "Risk 1 — LinkedIn ToS exposure at commercial scale (HIGH severity)" — HiQ Labs citation and framing match exactly | PASS — verbatim source citation |
| "Guest-endpoint JD hydration approach used in PoC cannot scale commercially; any commercial pivot requires a different LinkedIn ingestion layer" | "A commercial product using the guest-endpoint approach would face this exposure. The email-alert architecture for closed sources is the only low-risk commercial path; hydration would need to be replaced with a legitimate data agreement at commercial scale." (Risk 1) | PASS |
| Gate 1 — "≤5 min/day median triage on ≥80% of days over a 3-week window" | "The tool reduces daily job-search triage time from the current ~45 minutes to under 5 minutes on at least 80% of days over a 3-week measurement window." (Gate 1, Beta-Transition Decision Framework) | PASS — verbatim |
| Gate 2 — "≥3 relevant postings/week from non-LinkedIn sources over the MVP window" | "the tool surfaces at least 3 genuinely relevant postings per week that would not have appeared in a LinkedIn-only search" (Gate 2, Beta-Transition Decision Framework) | PASS — verbatim |
| Gate 3 — "User can name ≥2 reachable communities outside DS who share the same pain" | "The author can name at least 2 professional communities (beyond DS) who face the same cross-source aggregation + role-fit noise problem and who are reachable through channels" (Gate 3, Beta-Transition Decision Framework) | PASS — verbatim |
| "All three pass → Variant B candidate (commercial spike). Any fails → Variant A (stay personal)." | "If all three gates pass: the commercial thesis is worth a 2-week spike… If any gate fails: the tool stays personal." (Beta-Transition Decision Framework) | PASS — correctly hardened; "Variant B / Variant A" labels are PRD shorthands for the same binary outcome |
| No commercial infrastructure committed inside PoC scope | §6 Scope IN covers only the four technical milestones; §7 Scope OUT explicitly defers "Commercial distribution / managed-tier signups (Beta Variant B only)" | PASS — no premature commercial commitment |
| Commercial optionality preserved (not dropped) | Five hedges plus deferral of commercial scope explicitly to Beta Variant B constitute active optionality preservation, not commercial dropout | PASS |

---

### Analysis

PRD §3 does not soften any of the three Beta gates — they are reproduced verbatim from MARKET-ANALYSIS.md §"Beta-Transition Decision Framework" with no qualifying language added. The commercial verdict phrase ("Low-to-Medium, conditional on Beta gate validation") is also reproduced verbatim. The five architectural hedges are correctly framed as preserving optionality without altering personal-first scope — exactly the role MARKET-ANALYSIS.md assigns them via its Strategic Recommendations. The LinkedIn ToS commercial wall is explicitly acknowledged and correctly attributed. No PoC milestone in §6 Scope IN touches commercial infrastructure. The "Scope OUT" section explicitly names "Commercial distribution / managed-tier signups (Beta Variant B only)" — demonstrating that commercial optionality is preserved rather than abandoned.

There is one minor framing note (not a correction): MARKET-ANALYSIS.md §"PoC/MVP Implications" item 5 recommends documenting the M3 LLM benchmark as a "key input to the Beta monetisation decision." The PRD surfaces this benchmark as an optional opt-in at M3, which is consistent with DISCOVERY-NOTES.md §10 and does not contradict the market analysis. However, PRD §3 does not explicitly link the benchmark result to the monetisation framework (Path B — free local + paid cloud tier). This is a documentation gap, not a scope gap — the data will be captured; the PRD simply does not narrate its downstream use. If the architect wants to close it, one sentence in §3 or §6 M3 noting "M3 LLM benchmark results are input to Beta Path B evaluation (free local vs. paid cloud tier)" would complete the picture. This is a recommendation, not a required correction.

---

### Gaps and Corrections

| Severity | Location | Issue | Recommended edit |
|---|---|---|---|
| None — required | — | No misalignment found | — |
| Minor — optional | PRD §3 or §6 M3 | M3 LLM benchmark opt-in is not linked to Beta Path B (free local + paid cloud tier) monetisation evaluation, per MARKET-ANALYSIS.md PoC/MVP Implications item 5 | Add one sentence: "M3 benchmark results (if run) are input to Beta Path B evaluation — whether local-Ollama quality is equivalent to GPT-4o-mini determines whether a free/paid cloud tier is viable." |

No architect corrections are required before locking the PRD.

---

### Items for Ongoing PoC Alignment Reference

The following commitments in PRD §3 create future alignment anchors. Any new requirement touching these areas should be routed through business-analyst before being added to TASKS.

1. **Beta gates are hard thresholds** — all three must pass. Any proposal to add a fourth gate, soften a threshold, or credit partial results should be flagged as DRIFTING.
2. **Time-savings instrumentation (hedge 2) is logged in PoC, evaluated at MVP** — any proposal to do commercial evaluation of the analytics data *during PoC* would be scope-advancing into MVP territory and should be flagged as DRIFTING.
3. **Namespace-aware schema (hedge 3) is additive** — any proposal to implement actual multi-tenant logic (auth, per-user routing) inside PoC is VIOLATES.
4. **LinkedIn guest-endpoint hydration is personal-volume only** — any proposal to scale hydration throughput (batch jobs, parallelism) that would move toward commercial-volume request patterns violates the acknowledged commercial wall and LinkedIn ToS posture.
5. **Commercial distribution is deferred to Beta Variant B** — any proposal to add a setup wizard, onboarding flow, or distribution packaging during PoC or MVP should be flagged as DRIFTING.

---

- **Verdict**: ALIGNED
- **User decision**: Approved with documentation enhancement (optional gap addressed per BA recommendation)
- **Outcome**: Verdict accepted (ALIGNED, no required corrections). Optional documentation gap closed: PRD updated with one-sentence annotation linking the M3 LLM benchmark opt-in to the Beta Path B evaluation (whether local-Ollama quality matches GPT-4o-mini determines free-local + paid-cloud tier viability). PRD edit delegated to architect (parallel dispatch); see commit for SHA.

---

## 2026-04-26 — Indeed pagead resolution + per-email ingest log (TASK-M1-005b + TASK-M1-005c)

**Verdict**: TASK-M1-005b: ALIGNED | TASK-M1-005c: DRIFTING
**Mode**: B
**Anchors**:
- PRD §5 Scope IN — M1: "Indeed alert parser" and PRD §7 Success Criteria SC-2: "Indeed URL extraction from alert emails: ≥95%"
- PRD §5 Scope IN — M1: "JD hydration via LinkedIn / Indeed public guest endpoints (rate-limited 1 req / 30s)"
- TDD §C4 — Output contract: "≥95% URL extraction on ≥30 real Indeed alert emails (PRD SC-2)"; Responsibility (3): "Indeed redirect resolution: perform a single HEAD request through the redirect chain to resolve to the canonical posting URL (gated by the same 1 req/30s rate limit shared with C5)"
- TDD §C5 — Responsibility (2): "Apply a process-wide 1 request per 30 seconds rate limiter across LinkedIn + Indeed combined"
- PRD §8 Constraints R3: "LinkedIn / Indeed rate-limit or IP-block at hydration — Medium likelihood — degrade gracefully"
- ALIGNMENT-LOG 2026-04-24 anchor #4: "LinkedIn guest-endpoint hydration is personal-volume only — any proposal to scale hydration throughput (batch jobs, parallelism) that would move toward commercial-volume request patterns violates the acknowledged commercial wall and LinkedIn ToS posture."
- PRD §4 Phase Objectives: "Each milestone ends with a user-observable web-UI deliverable on real data."
- PRD §6 Scope OUT (cross-cutting): "Configurable knobs in config file — no hardcoded thresholds"

**Analysis — TASK-M1-005b (ALIGNED)**: The redirect-resolution behavior for Indeed `pagead/clk` URLs is already sketched in the TDD §C4 Responsibility (3), which explicitly mentions "Indeed redirect resolution: perform a single HEAD request through the redirect chain" — this requirement is not a new contract change but a clarification of a gap in how the TDD's Indeed redirect step was implemented (regex-only, missing the `pagead` URL format). Without this fix, PRD SC-2 (≥95% Indeed URL extraction) cannot be met at ~21% coverage, which would block M1 from closing. The volume (~40 calls/day combined with hydration) stays well within the "personal volume" anchor from the 2026-04-24 log entry; the stealth stack with jitter is consistent with the existing rate-limit posture in TDD §1.4 and §C5. This is a legitimate discovered-gap fix, not scope expansion.

**Analysis — TASK-M1-005c (DRIFTING)**: The per-email ingest log adds a new schema table and cross-cutting writer hooks to C3, C4, and C5, plus a new CLI reporting command. None of this is in PRD §5 Scope IN for M1, and the M1 "user-observable deliverable" is the web UI with applied/dismissed state — not a CLI telemetry report. The CLI report is a developer/debugging surface, not a user-facing triage workflow output, which means it doesn't serve PRD §4 Phase Objectives directly. It is useful (and honest) for M1-011 real-data validation cross-check, but it can be added as a lightweight addition if the user accepts the drift explicitly. None of the proposed deferred items (anomaly detection, UI integration) violate any Scope OUT clause — they are simply not in Scope IN. The `email_ingest_log` table and C3/C4/C5 writer hooks do expand the schema and each component's contract, which is substantive enough to flag as DRIFTING rather than trivially aligned.

**Recommendation**:
- TASK-M1-005b → ALIGNED: add to TASKS as M1-005b (fix to Indeed email parser, within the M1 milestone).
- TASK-M1-005c → DRIFTING: present the drift, then ask user: "Override and add to TASKS as M1-005c, or park in BACKLOG?"

**User decision**: M1-005b: Approved (ALIGNED). M1-005c: Approved with Override BA — user accepts DRIFTING risk because the ingest report tool directly enables more rigorous M1-011 validation and the Indeed pagead discovery confirms the value of per-email cross-check telemetry. Added to M1 scope.
**Outcome**: Both tasks added to TASKS.md as M1-005b and M1-005c, inserted between M1-009 (Done) and M1-010 (To Do). TDD.md updated by architect: §1.2a (new email_ingest_log table + indexes), §1.4 (dual rate-limit policy: 3-4.5s pagead resolution + 30s/req hydration), §C3/C4/C5/C11 (writer-hook contracts for the ingest log), §C4 Responsibility (3) (full 8-item stealth-stack contract for Indeed pagead resolution), §C27 (new component spec for the report CLI). Progress Summary updated: 14 total tasks, 9 Done, 5 To Do. M1-005c implementation requires gmail_message_id threading through the orchestrator (architect flagged as non-trivial plumbing). See commit for SHA.

---

## 2026-04-25 — Inactive state model replacing auto-remove: new status value, dedup bypass, MVP-M1 placement

**Verdict**: ALIGNED
**Mode**: B
**Anchors**:
- PRD §5 Scope IN — M1: "`applied` and `dismissed` state tables; state-aware Main view query"; M2: "Cross-state dedup generalised to canonical-id (a new posting matching an applied/dismissed canonical is suppressed from Main)"
- PRD §6 Scope OUT (Deferred to MVP): "Cron / launchd full automation (PoC: basic schedule + manual `/pipeline/run` only)"
- MARKET-ANALYSIS.md §"PoC/MVP Implications" item 4: "Tracking application state (the Applied/Dismissed flow) is table stakes for any commercial version. The PoC's state tracking must be at least as good as Huntr's free tier."
- MARKET-ANALYSIS.md §"Competitive Landscape" — Huntr: "No multi-source aggregation; no role-fit filtering; no immigration filter; no dedup" — state quality is the explicit commercial floor.
- TDD §1.2a `applied` table: `status TEXT -- Applied / Screen / Interview / Offer / Rejected / Ghosted`; `auto_remove_at TIMESTAMP -- applied_at + 90 days; null when status=Offer`
- TDD C7 §"Responsibility" (5): "`purge_stale_applied(user_id)` removes applied rows where `auto_remove_at < now AND status NOT IN ('Offer')`. The helper exists in M1; the scheduler that triggers it is deferred to MVP-M1."
- TDD C6 §"Output": `{status: 'new', …}` / `{status: 'seen', …}` — dedup is URL-keyed at M1, canonical-id-keyed from M2.

**Analysis**: The Inactive state model supersedes the auto-remove model entirely and is more coherent with the core value prop. Auto-remove was always a proxy for "this application has gone cold" — Inactive makes that semantic explicit and adds the forensic history the user wants. The dedup bypass (Inactive entries treated as non-existent for ingest dedup) is the load-bearing new behavior; it correctly extends the existing "cross-state dedup" pattern already documented in PRD §5 M2 ("a new posting matching an applied/dismissed canonical is suppressed from Main") by carving out a deliberate exception for cold applications. The schema impact on M1 is zero — `status` and `status_updated_at` already exist in the TDD `applied` table; the `auto_remove_at` column is dead code at M1 (scheduler deferred to MVP) and its removal or repurposing at MVP is additive, not a PoC regression. Placement at MVP-M1 is coherent because the full behavior requires a scheduler (already deferred to MVP) and status progression beyond `Applied` (not in M1 scope). The reminder feature is correctly identified as a separate MVP item and is not part of this requirement.

One prior ALIGNMENT-LOG anchor to note: the 2026-04-24 entry lists "Any proposal to add a setup wizard, onboarding flow, or distribution packaging during PoC or MVP should be flagged as DRIFTING" — this proposal does not touch any of those items. The other anchor — "No multi-tenant logic inside PoC" — is also untouched; the change is single-user throughout.

**Recommendation**: ALIGNED — ask user: "Add to BACKLOG.md as MVP-M1 design item, or park it for now?"

**User decision**: Approved (Option A — full capture: BACKLOG + PRD + TDD updates)
**Outcome**: Added to BACKLOG.md as MVP-M1 design item ("Inactive state lifecycle — supersedes auto-remove model"). PRD.md updated (§5 M2 cross-state dedup bullet extended with Inactive-bypass exception; §6 Scope OUT gained two new "Deferred to MVP" lines for Inactive lifecycle + reminder). TDD.md updated (§1.2a applied table and §C7 Responsibility (5) gained "superseded at MVP-M1" notes for auto_remove_at column and purge_stale_applied helper). M1 untouched — TASK-M1-007 stands as shipped. PRD/TDD/BACKLOG edits delegated to architect (parallel dispatch); see commit for SHA.

---

## 2026-04-26 — Expired status for dead-link postings (extends Inactive state lifecycle BACKLOG entry)

**Verdict**: ALIGNED
**Mode**: B
**Anchors**:
- PRD §5 Scope IN — M2: "Cross-state dedup generalised to canonical-id... Exception: a new posting matching a canonical that is currently in `Inactive` state is NOT suppressed — Inactive entries are treated as non-existent for dedup purposes (both URL-based and LLM content-based)."
- PRD §5 Scope IN — M1: "JD hydration via LinkedIn / Indeed public guest endpoints (rate-limited 1 req / 30s)"
- PRD §5 Scope IN — M1: "`applied` and `dismissed` state tables; state-aware Main view query"
- PRD §4 Phase Objectives: "Each milestone ends with a user-observable web-UI deliverable on real data."
- BACKLOG.md — MVP-M1 Inactive state lifecycle: "Dedup bypass: Inactive entries are treated as non-existent for BOTH URL-based and LLM content-based dedup."
- ALIGNMENT-LOG 2026-04-25 Inactive entry — Analysis: "The dedup bypass (Inactive entries treated as non-existent for ingest dedup) is the load-bearing new behavior; it correctly extends the existing 'cross-state dedup' pattern already documented in PRD §5 M2"

**Analysis**: Expired is semantically distinct from Inactive (system-failure vs. cold-application) and from Dismissed (system-unavailable vs. user-uninterested). The dedup bypass mechanic is architecturally identical to Inactive, and the primary trigger (hydrator HTTP 404 auto-mark Expired) is a natural extension of C5/C6 which are already in MVP-M1 scope for the dedup bypass wiring. Bundling Expired into the existing MVP-M1 BACKLOG entry is coherent — both statuses share the same implementation pattern (new status value, dedup bypass, UI sub-section) and implementing the pattern twice in separate milestones is waste. The manual-button fallback is appropriately phased to MVP-M2, keeping the MVP-M1 scope increment minimal. The Expired concept does not touch any Scope OUT clause and does not contradict any existing PRD principle. No pattern of repeated status-model drift has been observed across prior log entries — this is the second status addition (Inactive being the first) but both are grounded in concrete real-world edge cases, not speculative coverage.

**Recommendation**: ALIGNED — bundle Expired into the existing MVP-M1 BACKLOG entry ("Inactive state lifecycle"). Ask user: "Add Expired to the MVP-M1 BACKLOG entry now, or park it for now?"

**User decision**: Approved — bundle Expired with Inactive at MVP-M1 (auto-detect via hydrator HTTP 404 only; manual "Job link is dead" button deferred to MVP-M2 per BA recommendation).
**Outcome**: BACKLOG.md updated by architect: existing "MVP-M1 — Inactive state lifecycle" entry renamed to "Inactive AND Expired state lifecycle"; scope expanded from 5 items to 6 (added Hydrator auto-detect on HTTP 404 → mark_expired); status enum reconciliation caveat extended to include Expired; M1 workaround documented (users use Dismiss for dead links until MVP-M1 lands proper Expired handling). PRD.md updated: §5 M2 dedup-bypass exception extended to Inactive OR Expired; §6 Scope OUT lifecycle line gained Expired clauses. TDD.md updated: §C7 supersession note now references mark_expired alongside auto_inactivate; §C5 (Hydrator) gained a 2026-04-26 note about HTTP 404 detection. M1 untouched. See commit for SHA.

---

## 2026-04-27 — Milestone 1 closure

**Verdict**: ALIGNED
**Mode**: B
**Anchors**:
- PRD §5 Scope IN — M1 user-observable deliverable (ROADMAP §M1): "Open `localhost:PORT`, see a stack of new postings from today's LinkedIn + Indeed emails with title/company/location/URL/source. Click a card → expand → click apply URL → goes to LinkedIn/Indeed. Click `[Mark Applied]` → posting moves to Applied tab. Click `[Dismiss]` → posting moves to Dismissed tab and is permanently blacklisted. Re-run pipeline → same URLs ingested today no longer appear in Main, and applied/dismissed postings stay out of Main. No content-aware dedup, no fit score, no tags yet."
- PRD §4 Phase Objectives: "Each milestone ends with a user-observable web-UI deliverable on real data."
- PRD §3 Commercial Thesis (Agreed): "Personal-first throughout PoC and MVP." + five hedges threaded into milestones.
- ALIGNMENT-LOG 2026-04-24 anchors (Beta gates untouched; hedge 2 events table; namespace-aware schema; personal-volume hydration; no commercial distribution).
- BACKLOG.md — MVP-M1 — Inactive AND Expired state lifecycle; MVP-M1 — Sync progress feedback.
- TASK-M1-011 quality log: 91/91 postings hydrated (100%); all 9 M1 ACs PASS.
- TASK-M1-012 quality log: user-approved verbatim ("All function work"); 9/9 ACs PASS.

**Analysis**: All 14 M1 tasks are Done and the 9 ROADMAP M1 acceptance criteria are met at or above threshold — URL extraction 100%/100% (LinkedIn/Indeed) vs ≥95% bar; hydration 100% vs ≥95% bar; URL dedup 100%; state persistence 100%; events instrumentation verified; repo public with badge. The user-observable deliverable matches the ROADMAP §M1 verbatim description across every element (three tabs, card expand, apply URL opens, applied/dismissed state, dedup across re-runs). Six scope additions landed during M1: (1) un-apply symmetric to restore — user-approved, symmetric UX completion; (2) new/viewed inbox sort + card greying — UX polish, does not contradict any Scope IN or OUT clause; (3) JSON-LD Indeed extraction path — extends TDD §C5 to handle Cloudflare 403, required to reach the ≥95% hydration bar; (4) per-email ingest log + report CLI (M1-005c) — Override BA, DRIFTING verdict explicitly accepted by user, logged 2026-04-26; (5) Indeed pagead URL resolution (M1-005b) — ALIGNED, required to reach ≥95% Indeed URL extraction; (6) HTML-to-text strip + paragraph preservation + click-to-select — UX fixes surfaced by real-data validation, not commercial additions. None of the six additions touch PRD §6 Scope OUT or any of the five 2026-04-24 alignment anchors. The commercial thesis anchors are all untouched: Beta gates are hard thresholds (not evaluated at PoC), hedge 2 instrumentation (events table) populates but the analytics UI surface is deferred to M4, namespace-aware schema remains `user_id='default'` with no multi-tenant logic, hydration stays at 1 req/30s personal volume, and no commercial distribution packaging was added. Both BACKLOG items (Inactive/Expired lifecycle and sync progress feedback) are correctly scoped to MVP-M1 and do not creep into PoC M2/M3/M4 scope.

**Recommendation**: ALIGNED — approve M1 closure. No revision required.

Caveats for user's awareness at approval:
1. M1-005c (per-email ingest log + CLI) was logged as a DRIFTING override on 2026-04-26. The component is live and working; the drift was accepted explicitly. No further action required.
2. TASK-M1-012 quality log notes 5/21 Indeed postings (DOM-fallback path) render as wall-of-text due to HTML structure differences from JSON-LD path. This is not an M1 AC failure (hydration_status is complete; text is present), but it is a UX gap noted for MVP.
3. Sync progress feedback gap (no visible progress during 30–45 min hydration run) is captured in BACKLOG.md as MVP-M1. Not a blocker.

**User decision**: Approved (explicit "approve" response during /milestone-complete)
**Outcome**: M1 formally closed 2026-04-27. All 14 tasks Done; all 9 ROADMAP §M1 ACs PASS; user-approved verbatim. TASKS.md updated by architect (M1 moved to Completed Milestones Log). CLAUDE.md state pointers will be updated by main session. PoC phase continues — next: /milestone-plan jd-matcher for Milestone 2 (Content-aware dedup + repost detection per ROADMAP §M2). See commit for SHA.

---

## 2026-04-27 — Indeed extraction deferred to MVP; PoC scope reduced to LinkedIn-only

**Verdict**: DRIFTING
**Mode**: B
**Anchors**:
- PRD §7 Success Criteria SC-2: "Indeed URL extraction from alert emails ≥95% — Validated in M1" — M1 already passed this SC at 100%; the issue is whether Indeed remains an active PoC source in M2+
- PRD §7 Success Criteria SC-3: "JD hydration (LinkedIn + Indeed guest endpoints) ≥95% — Validated in M1" — same status
- PRD §7 Success Criteria SC-8: "Cross-source merge — Verified — ≥3 real LinkedIn + Indeed pairs collapse to one card — Validated in M2"
- PRD §5 Scope IN M2: "M2 cross-source merge ACs validated against LinkedIn↔Indeed pairs only" (Himalayas deferral note)
- PRD §5 Scope IN M1: "Gmail API ingestion of LinkedIn + Indeed alert emails"; "Indeed alert parser"; "JD hydration via LinkedIn / Indeed public guest endpoints (rate-limited 1 req / 30s)"
- PRD §4 Phase Objectives (1): "Multi-source ingestion (Gmail email parsing for LinkedIn/Indeed/Job Bank + JD hydration; direct-API polling for Himalayas/Remotive/Jobicy/HN)"
- MARKET-ANALYSIS.md Beta Gate 2: "the tool surfaces at least 3 genuinely relevant postings per week that would NOT have appeared in a LinkedIn-only search (i.e., came from Himalayas, Job Bank, HN Hiring, or Remotive)" — Indeed is not named as a Gate 2 source; Gate 2 is met by M4 open-API sources
- PRD §9 Risks R3: "LinkedIn / Indeed rate-limit or IP-block at hydration — Medium likelihood — degrade gracefully"

**Analysis**: DRIFTING rather than VIOLATES because three factors bound the severity. First, M1 already closed with SC-2 and SC-3 both passing at 100% — Indeed parsing and hydration are proven PoC capabilities; this deferral removes Indeed from active M2+ execution, not from the proven record. Second, the commercial thesis (MARKET-ANALYSIS.md Gate 2) explicitly names Himalayas/Job Bank/HN/Remotive as the non-LinkedIn proof sources — Indeed is not the Gate 2 gate-keeper, so the commercial thesis survives LinkedIn-only PoC execution intact. Third, the blocking cause is a realized version of PRD §9 R3 (IP-level Cloudflare block) compounded by a hardware constraint (MDM-disabled remote debugging port on employer machine) that prevents all bypass paths — this is a documented technical constraint, not a preference change. The three concrete impacts that make this DRIFTING rather than ALIGNED: (a) SC-8 cross-source merge ("≥3 real LinkedIn↔Indeed pairs collapse to one card") becomes unevaluable on live data with Indeed inactive — must shift to synthetic pairs or be reframed as "≥3 verified cross-source pairs"; (b) TASK-M2-012 calibration assumed some real cross-source pairs for labeling — with Indeed inactive those pairs are unavailable from the live pipeline; (c) PRD §4 Phase Objective 1 names "LinkedIn/Indeed/Job Bank + JD hydration" as the multi-source ingestion proof — LinkedIn-only narrows the closed-platform proof from two sources to one, which is a visible scope reduction even though the dedup technique milestone is otherwise intact. The browser_fetcher.py infrastructure (patchright Tier 1 + CDP Tier 2) was built and is an asset for MVP Indeed work; it does not need to be deleted.

**Recommendation**: DRIFTING — override and proceed, or park?

Specific items requiring a decision if user overrides:
1. SC-8 revision: "≥3 real LinkedIn↔Indeed pairs" → "≥3 verified cross-source pairs (synthetic pairs acceptable if live Indeed data unavailable due to IP-block)" — or mark SC-8 deferred to MVP
2. TASK-M2-012: calibration report documents Indeed-inactive status; real-data labeling uses LinkedIn-only live pairs + synthetic cross-source pairs
3. BACKLOG additions:
   - "Indeed via Playwright on personal non-MDM machine" → MVP-M1
   - "Indeed via commercial proxy (Oxylabs/Bright Data or equivalent)" → MVP-M1 alternative path
   - "browser_fetcher.py (patchright Tier 1 + CDP Tier 2) built and disabled for PoC" → note as MVP-M1 infrastructure asset ready to activate
4. PRD §4 Phase Objective 1: add parenthetical "(Indeed deferred to MVP — IP-level Cloudflare block + MDM hardware constraint on employer machine; PoC validates LinkedIn email ingestion + open-API sources)"
5. PRD §9 Risks R3: add realized-risk note — "Indeed Cloudflare block realized 2026-04-27 at PoC M2; deferred to MVP"

**User decision** (2026-04-28): Approved with Override BA — defer Indeed extraction to MVP-M1; PoC scope reduced to LinkedIn-only. SC-8 resolved per Option A (synthetic cross-source pairs acceptable; the C21 dedup mechanism is proven on synthetic by design per TDD §C21 sample-selection "Hybrid"). browser_fetcher.py infrastructure stays committed as MVP-ready asset.

**Outcome** (2026-04-28): Architect updated PRD/TASKS/BACKLOG/DATA-SOURCES per the BA shopping list. Specifically:
- PRD §4 Phase Objective 1: parenthetical added deferring Indeed to MVP with §9 R3 reference
- PRD §7 SC-8: revised to accept synthetic cross-source pairs (Option A), with reasoning anchored to TDD §C21 sample-selection
- PRD §9 R3: realized-risk note added with full root cause (Cloudflare IP-block + MDM-disabled debug port) and mitigation (defer to MVP-M1 with browser_fetcher.py ready-to-activate)
- PRD §5 M2: cross-source merge clause revised — real merged cards may be LinkedIn-only; multi-source UI mechanic demonstrated via synthetic C21 fixtures
- TASKS.md TASK-M2-012: AC added explicitly stating synthetic cross-source pairs acceptable per PRD §9 R3
- TASKS.md TASK-M2-013: AC revised — sync demo no longer requires live Indeed cross-source merged card; SC-8 verification proceeds via synthetic fixture path
- BACKLOG.md: 3 new MVP-M1 entries added (Indeed via personal machine / via commercial proxy / browser_fetcher.py asset note)
- DATA-SOURCES.md: PoC status note appended to Indeed section
M1 untouched (SC-2 + SC-3 already PASSED at M1; Indeed parsing + hydration are proven). Commercial thesis intact: Beta Gate 2 names Himalayas/Job Bank/HN/Remotive (not Indeed) as the non-LinkedIn proof sources, so LinkedIn-only PoC execution preserves the Beta evaluation surface. browser_fetcher.py committed by main session in a separate follow-up commit. See commit for SHA.

---

## 2026-04-29 — Add `role_orientation: list[str]` field to C18 canonical extraction (M2 / TASK-M2-006b Phase B)

**Verdict**: DRIFTING
**Mode**: B
**Anchors**:
- PRD §5 Scope IN M2: "LLM extraction call producing `canonical_company / canonical_seniority / canonical_location / team_or_department / top_skills / role_summary` (used here for normalisation only — full classification deferred to M3)"
- PRD §5 Scope IN M3: "Single LLM extraction prompt... producing all of: canonical fields + salary + tags + `primary_focus` + `fit_score` + `fit_reasoning` + `requires_pr_or_citizenship`"
- TDD §1.0 M2 scope note: "steps 6 (LLM extraction — normalisation only, full classification still deferred to M3)"
- TDD §1.0 FUSE formula (M2): "`0.4 × embedding_cosine(role_summary) + 0.3 × jaccard(top_skills) + 0.2 × title_cosine + 0.1 × seniority_match`" — role_orientation is not a current FUSE term
- PRD §4 Phase Objectives (2): "Content-aware deduplication (LLM-extracted fields + embedding similarity, two-stage)"
- PRD §5 Scope IN M4: "CV text extraction... cosine rank against `role_summary + top_skills` embedding" — role_orientation is listed as a downstream use for M4 CV matching, which is out of M2 scope

**Analysis**: The verdict is DRIFTING, not VIOLATES, for three reasons. First, the field is classification — not normalisation. PRD §5 M2 explicitly confines the LLM extraction call to normalisation fields; the full classification layer (tags, focus, score, reasoning) is M3 scope. `role_orientation` is a classification tag (it categorises the role's mode of work), which makes it an M3 or later addition by PRD §5's own logic — adding it at M2 expands the extraction contract beyond the stated M2 boundary without changing the PRD. Second, both primary downstream uses are out of M2 scope: C21 FUSE (this milestone) does not include orientation as a FUSE term per TDD §1.0, so adding the field now gives M2 no observable benefit; M4 CV matching and UI filtering are later milestones. The field would sit inert in the schema through M2 and M3. Third, the proposal is not a VIOLATES because the field does not touch any PRD §6 Scope OUT clause (it is not auto-apply, CV rewriting, auth, billing, or any listed deferred category), and the implementation cost (~100 LOC, zero incremental LLM cost) is genuinely low. What makes it DRIFTING rather than ALIGNED: it expands the M2 LLM extraction contract beyond the normalisation-only boundary stated in PRD §5 M2, adds a schema column with no M2 or M3 AC attached to it, and produces no user-observable deliverable within the current milestone. Pattern note: this is the second non-normalisation field proposed for the M2 extraction pass (after top_skills canonicalization in M2-006b). No escalating drift pattern is observed — both are anchored to real downstream M4 uses — but the accumulation of M3/M4-serving fields into the M2 extraction prompt bears watching.

**Recommendation**: DRIFTING — present the drift, then ask: "Override and add to TASK-M2-006b in-place, or park as BACKLOG item targeting M3?"

Preferred framing if user overrides: add as a clearly-labelled sub-item inside TASK-M2-006b Phase C (prompt patch) with an explicit note that the field is M3/M4-serving, has no M2 AC, and its first measured quality check is deferred to M3 hand-label pass. Do not create a separate TASK-M2-006c — the implementation is small enough that a sub-item inside the active task is sufficient, and keeping it bundled avoids a phantom task with no AC of its own.

Preferred framing if user parks: add to BACKLOG.md as "M3-candidate — `role_orientation` classification field (Engineering / Problem-Solving / Communication) — add to M3 single extraction prompt pass alongside tags and primary_focus; M4 CV matching and UI filter downstream uses; no FUSE weight in M2 per current TDD §1.0." This is the cleaner landing zone because M3 is already expanding the extraction prompt to full classification — `role_orientation` slots naturally into that expansion with a real AC (e.g., ≥80% label agreement on the 30 M3 hand-labeled postings, same set as SC-9/SC-10).

**User decision**: Accepted Recommendation B — defer `role_orientation` to M3 alongside the full classification expansion. Field will NOT be added to M2-006b scope.
**Outcome**: BACKLOG entry created under "Deferred to PoC M3 — role_orientation classification field" per Gate 2 protocol. TASK-M2-006b proceeds with top_skills canonicalization only (purely technical, 43-entry taxonomy). No schema change at M2. M3 will add `role_orientation` to the expanded classification prompt alongside tags, primary_focus, fit_score, and fit_reasoning, with a ≥80% label-agreement AC on the M3 30-posting hand-label set. See BACKLOG.md for full implementation spec. Logged 2026-04-29.

---

## 2026-04-29 — User decision follow-up: role_orientation defer accepted (TASK-M2-006b Phase B)

- **Triggered by**: TASK-M2-006b Phase B completion — user reviewed BA DRIFTING verdict above
- **Mode**: follow-up (no new BA analysis required)
- **References**: BA entry immediately above (same date), BACKLOG.md "PoC-M3 — role_orientation"

**User decision**: Accepted BA Recommendation B (defer `role_orientation` to M3). No override.
**Action taken**: BACKLOG entry created (per Gate 2 step 3, user said defer). TASK-M2-006b Phase C–E proceeds without `role_orientation`. ALIGNMENT-LOG updated.
**Outcome**: Logged per Gate 2 protocol. No ALIGNMENT-LOG amendment required — BA verdict stands as DRIFTING with user deferral, no override.

---

## 2026-04-29 — Gate 4 user approval: TASK-M2-006b probabilistic result (75.3% canonical match rate)

- **Triggered by**: TASK-M2-006b Phase E completion — AC "≥80% canonical match rate" landed at 75.3% (910/1209 mentions). Per Gate 4 (CLAUDE.md), probabilistic-tier results require explicit user approval before a task can be marked Done.
- **Mode**: Gate 4 user approval (no BA dispatch needed — quality decision, not scope decision)
- **Independent verification**: test-validator confirmed the 75.3% rate via direct SQL query against `extraction_cache` (910/1209 mentions match a canonical taxonomy entry). LLM mapping compliance verified at ~99% (13 mentions / 1.08% are mapping misses; remaining ~23% are legitimate technical tail skills outside the 43-entry DS/ML-core taxonomy — Docker, dbt, R, Tableau, Snowflake, Kafka, Java, etc.). M2-006 baselines independently verified to hold (company 100%, seniority 100%, location 100% on a different 30-posting sample).

**User decision**: Approved 75.3% as Done. The AC threshold (≥80%) was set before the natural skill distribution was known; the 75.3% reflects taxonomy coverage scope, not LLM compliance defect (~99% compliance on in-taxonomy skills, which is what FUSE Jaccard quality actually depends on). Tail skills appearing in their natural form is acceptable — Jaccard still matches across postings using the same surface form.

**Outcome**: TASK-M2-006b is genuinely Done. Task closure stands at commit `f907431`. BACKLOG already carries the M3 taxonomy expansion candidate (with concrete tail-skill proposals: dbt, Docker, Tableau, R, Airflow, Snowflake, Kafka, LangChain) for re-evaluation when the M3 full-classification prompt overhaul lands. Pipeline advances to TASK-M2-007 (Embedding Pipeline C20).

**Minor process gaps noted (not addressed under Option A approval)**:
- Stale "Awaiting user taxonomy review" header in `docs/poc/quality-logs/TASK-M2-006b-skills-analysis.md` (Phase A header not updated for Phase E)
- Test marker mismatch: `tests/llm/test_canonical_skills_regression.py` uses `@pytest.mark.skipif(SKIP_LIVE,...)` instead of `@pytest.mark.live` — `pytest -m live` returns 0 tests (functional behavior is correct under `SKIP_LIVE=0`)
- Mapping-miss count in `docs/poc/quality-logs/TASK-M2-006b.md` says "12 mentions / <1%"; actual is 13 / 1.08%

User chose Option A (approve as-is) over Option C (approve + fix Minors); these are documentation/marker hygiene items deferred to a future cleanup pass if surfaced again.

---

## 2026-04-29 — LLM-based dedup fallback for borderline similarity scores (fuzzy zone 0.85–0.95)

**Verdict**: DRIFTING
**Mode**: B
**Anchors**:
- PRD §5 Scope IN M2: "Two-stage dedup: block by `(canonical_company, canonical_seniority, canonical_location)`; fuse cosine + structured similarity at 50/50" — the dedup engine is defined as a deterministic two-stage mechanism with a fixed threshold
- PRD §5 Scope IN M2: "LLM extraction call producing `canonical_company / canonical_seniority / canonical_location / team_or_department / top_skills / role_summary` (used here for normalisation only — full classification deferred to M3)"
- PRD §10 Open Question #4: "Auto-merge similarity threshold — default 0.90 from DISCOVERY-NOTES.md §10; calibrated against hand-labeled 30 pairs at M2" — threshold calibration is the M2 answer to borderline ambiguity; the PRD's explicit mechanism is calibration, not LLM fallback
- TDD §1.0 M2 scope note: "steps 6 (LLM extraction — normalisation only, full classification still deferred to M3)" — M2's LLM budget is scoped to normalisation; a dedup classifier is a new classification task, not normalisation
- TDD §1.0 FUSE formula: "`0.4 × embedding_cosine(role_summary) + 0.3 × jaccard(top_skills) + 0.2 × title_cosine + 0.1 × seniority_match`; auto-merge at strict threshold 0.90" — the TDD defines the FUSE result as the final authority at M2
- CLAUDE.md Gate 4: "Real data — probabilistic: no fixed threshold. Always flag to user for approval before task can be marked Done" — an LLM classifier in the dedup path converts a deterministic step into a probabilistic one, triggering Gate 4's user-approval requirement on every pair in the fuzzy zone

**Analysis**: DRIFTING, not VIOLATES, for two reasons. First, the LLM-fallback does not contradict any PRD §6 Scope OUT clause — it is not auto-apply, CV rewriting, auth, billing, or any listed deferred category. Second, it is conceptually consistent with PRD §4 Phase Objective 2 ("content-aware deduplication") — using full JD text is literally the richest content signal. What makes it DRIFTING rather than ALIGNED: PRD §5 M2 defines the dedup engine with a fixed threshold calibrated at M2-end (Open Question #4) as the resolution mechanism for borderline cases. An LLM fallback is an entirely different resolution strategy that (a) changes the M2 dedup engine from deterministic to probabilistic, triggering Gate 4 user-approval on every fuzzy-zone pair; (b) introduces a new LLM task (dedup classification) beyond the normalisation-only M2 LLM scope; and (c) supersedes the calibration task (TASK-M2-012) as the primary answer to PRD §10 Open Question #4 without that calibration data yet existing. The Galent/Alquemy edge cases motivating the proposal are genuine, but the right M2 answer per PRD §10 is: run the calibration (M2-012), observe the distribution, and decide then whether the threshold alone is sufficient. On Gate 4: even at low cost (~$0.006/corpus), the LLM's binary yes/no verdict is non-deterministic — test-validator cannot produce a pass/fail against a fixed standard without user approval on every borderline pair. This is a process overhead that inflates M2 closure complexity.

Pattern note: this is the third proposal in M2 to add LLM capability beyond the normalisation-only boundary defined in PRD §5 M2 (role_orientation was the second; both were DRIFTING). The pressure is consistently in the same direction — enriching the M2 extraction/decision layer toward M3-class intelligence. The pattern is understandable (edge cases surface real gaps), but it bears watching across M2-end. The right containment is TASK-M2-012 calibration first.

No LLM-fallback precedent exists in TDD or PRD. The closest thing is TDD §1.0's note that local Ollama is config-swappable — but that is a provider swap, not a decision-delegation pattern.

**Recommendation**: DRIFTING. Recommended landing zone: **defer to TASK-M2-012 (M2 calibration)**. Specifically: run the 30-pair hand-label, measure the threshold, and explicitly count how many pairs fall in 0.85–0.95. If the count is material (e.g., >3 out of 30), present the LLM-fallback then as a scoped M2 addition with calibration data in hand. If the count is 0–1, the threshold alone is sufficient and the LLM-fallback moves to BACKLOG targeting M3.

Alternative landing zones in decreasing preference:
1. TASK-M2-012 decision point (recommended above) — preserves calibration-first intent of PRD §10 Open Question #4
2. BACKLOG as explicit PoC-M3 candidate — bundles with the M3 classification layer, which already uses full-JD LLM calls; adding a dedup-classifier prompt in M3 is lower marginal cost and the staffing-firm pattern will be better characterized by then
3. New in-place TASK-M2-008b (NOT recommended) — bypasses the calibration evidence that PRD §10 prescribes and makes M2 close with a probabilistic Gate 4 component before the threshold is even tuned

**User decision**: Accepted BA Recommendation A — defer to TASK-M2-012 calibration (conditional re-evaluation based on fuzzy-zone hit rate)
**Outcome**: BACKLOG updated (new "Conditional — re-evaluate at TASK-M2-012" section); TASKS.md TASK-M2-012 gains 2 new ACs; TASK-M2-008 ships unchanged

---

## 2026-04-29 — User decision follow-up: LLM-fallback dedup classifier deferred to TASK-M2-012 conditional re-evaluation

- **Triggered by**: BA verdict DRIFTING on LLM-fallback dedup classifier proposal (same date, see entry above)
- **Mode**: follow-up (no new BA analysis required)
- **References**: BA entry immediately above (DRIFTING verdict + recommendation), `docs/poc/BACKLOG.md` "Conditional — re-evaluate at TASK-M2-012", `docs/poc/TASKS.md` TASK-M2-012 (added two new ACs: fuzzy-zone count + Galent-pattern title-cosine review)

**User decision**: Accepted BA Recommendation A — defer the decision to TASK-M2-012 calibration. Re-evaluate based on fuzzy-zone hit rate from the 30-pair hand-labeled calibration set:
- If ≥3 of 30 pairs land in the 0.85–0.95 fuzzy zone (material): promote LLM-fallback to M2 addition with calibration data in hand
- If 0–2 of 30: threshold tuning is sufficient; move BACKLOG entry to "Deferred to PoC M3" (Smart layer expansion already covers full-JD LLM calls)

**Action taken**:
- BACKLOG.md: new "Conditional — re-evaluate at TASK-M2-012" section added with full implementation sketch + conditional re-evaluation rules
- TASKS.md TASK-M2-012: two new acceptance criteria added — (1) count fuzzy-zone pairs and decide promote/defer; (2) Galent-pattern title-cosine review for borderline cases where skills_jaccard=1.0 + seniority_match=1.0 but title drags score down
- TASK-M2-008 (commit `45d9196`) is unchanged — the dedup engine ships as-is for M2 with the deterministic FUSE math + threshold

**Pattern note**: This is the third M2 proposal to expand the LLM layer beyond normalisation that has been DRIFTING-deferred (after `role_orientation` to M3, plus the full_jd-fallback safety check that WAS added defensively at M2-008). The PRD's prescribed containment valve (TASK-M2-012 calibration) is being honored.

---

## 2026-04-29 — Surface M2-available LLM fields in collapsed card (post-TASK-M2-011 UI validation)

**Verdict**: ALIGNED
**Mode**: B
**Anchors**:
- PRD §5 Scope IN M2: "LLM extraction call producing `canonical_company / canonical_seniority / canonical_location / team_or_department / top_skills / role_summary` (used here for normalisation only — full classification deferred to M3)"
- PRD §4 Phase Objectives: "Each milestone ends with a user-observable web-UI deliverable on real data."
- UX-SPEC.md §1 M2 end-state: "No new UI controls at M2. The merge and repost indicators are read-only signals."
- ALIGNMENT-LOG 2026-04-29 (role_orientation deferral): salary and `role_orientation`/DS-fit already explicitly deferred to M3 per prior BA verdict; this proposal does not revisit those.

**Analysis**: The user has decided to surface LLM output on cards; the alignment question is which M2-available fields are safe to display now vs. which require M3 companion logic. Four fields pass the user's criterion ("user can act on / interpret standalone"): `canonical_seniority` (readable fit signal, no downstream logic), `team_or_department` (org unit context, null-safe render), `top_skills` (skill chip strip; Jaccard already runs inside FUSE dedup, display is additive only), and `role_summary` first-sentence teaser (role-at-a-glance before expand). All four already exist in `canonical_postings` — zero new extraction, zero new schema columns, zero probabilistic components. Salary is correctly excluded (not in M2 schema; M3 extraction adds it). `role_orientation`/DS-fit is correctly excluded (explicitly deferred to M3 per prior BA log entry). No PRD §6 Scope OUT clause is touched. The additions are read-only display signals, consistent with the UX-SPEC M2 pattern.

**Recommendation**: ALIGNED — ask user: "Add as TASK-M2-014 (card UI enrichment) or park for now?"

**User decision**: Approved (TASK-M2-014 added to M2 scope — completed 2026-04-29, commit 7ea5674)
**Outcome**: TASK-M2-014 implemented: seniority chip, team line, role_summary teaser, skills strip in expanded view. 886 tests pass. Committed and pushed.

---

## 2026-04-29 — Six UX proposals raised during live M2 re-validation (post-TASK-M2-014)

**Verdict**: A: ALIGNED | B: ALIGNED | C: DRIFTING | D: ALIGNED (user-deferred) | E: ALIGNED (user-deferred) | F: ALIGNED (user-deferred)
**Mode**: B
**Anchors**:
- PRD §4 Phase Objectives: "Each milestone ends with a user-observable web-UI deliverable on real data."
- PRD §5 Scope IN M2: card UI is the deliverable surface; "No new UI controls at M2" was the pre-M2-014 constraint; TASK-M2-014 (ALIGNED) established that field-reordering and skill-strip display are within scope as long as no new schema/extraction/probabilistic component is introduced.
- UX-SPEC.md §1 M1/M2 end-state: card layout defined in §1; keyboard shortcuts in §6 include `e` (toggle expand/collapse focused card) and `j/k` navigate — both depend on a single-column card list.
- UX-SPEC.md §7 "What the PoC UI Explicitly Does NOT Have": no pagination, no search/filter in PoC (absence is implicit; no explicit deferral clause exists for search/filter, but PRD §6 Scope OUT does not mandate them for M2 either).
- PRD §6 Scope OUT (Deferred to MVP): "Soft-rank weight UI sliders, fit-score threshold slider, tag taxonomy editor" — filter-by-metadata is in the same spirit, not explicitly listed but consistent with the MVP-level interactive UI refinement framing.
- TDD §1.0 Solution Approach: "Surface — FastAPI serves a single HTML page on `localhost:PORT` with three tabs (Main / Applied / Dismissed). Keyboard-first triage; cards expand in place." — "expand in place" is the contractual interaction model for the card list. Two-pane layout replaces this model.
- TDD §1.2 Component Inventory, Web UI: "FastAPI app + HTML/JS — three tabs, card list, expand-in-place, keyboard shortcuts, Settings, Analytics" — "expand-in-place" is embedded in the TDD component contract for C9.
- UX-SPEC.md §6 Keyboard Shortcuts: "`e` | Toggle expand / collapse focused card" — this shortcut is only meaningful in a single-column expand-in-place model; two-pane replaces the need for it and breaks the handler.
- ROADMAP.md (CLAUDE.md document path): MVP-M1 is the reliability/UX hardening phase; UX architecture changes are correctly placed there per the three-phase framework (CLAUDE.md: "MVP phase: Harden the proved prototype… UX refinement").

**Analysis — A (layout reshuffle)**: Reordering fields already in `canonical_postings` onto the collapsed card is purely template + CSS. Zero new schema columns, zero new extraction calls, zero probabilistic components. The change is tighter than TASK-M2-014 (which added fields from expanded-only into collapsed view and was ALIGNED). No PRD anchor is violated; the M2 deliverable (user-observable card UI on real data) is directly improved. ALIGNED.

**Analysis — B (skills move collapsed → expanded is now reversed to collapsed-always)**: `top_skills` was placed in expanded-only by TASK-M2-014. Moving it to the collapsed card is a one-line template change — the data already lives in `canonical_postings.top_skills` and the chip strip component already exists. No new extraction, no schema change. This is exactly the kind of display-policy decision TASK-M2-014 established as in-scope. ALIGNED.

**Analysis — C (two-pane master-detail)**: DRIFTING. The current TDD §1.0 and UX-SPEC §1/§6 define the interaction model as "expand-in-place" with keyboard shortcuts `e` (expand/collapse), `j/k` (navigate card list). Two-pane master-detail replaces this model wholesale: `e` becomes meaningless (or must be redefined), the HTMX strategy shifts from in-place card swap to right-pane content load, and C9 (Web UI component) must be substantially reworked. The right pane is a new DOM region with its own state (which card is "focused"), its own loading behaviour, and its own scroll context. This is not a CSS/template change — it is a frontend architecture change. Additionally, two-pane is a natural companion to pagination, search, and filter (D/E/F), all of which the user has self-triaged to MVP-M1. Implementing the pane structure in M2 without its companions (pagination/search) creates a half-finished master-detail that the user would revisit immediately in MVP-M1 anyway. Per the three-phase framework (CLAUDE.md), "UX refinement" is explicitly an MVP-M1 concern; PoC UX is validated, not polished. The DRIFTING verdict (not VIOLATES) reflects that two-pane does not contradict any PRD §6 Scope OUT clause — it simply isn't in TDD §1.0 / C9 contract, and shipping it now without D/E/F creates premature architectural commitment before those companions are planned.

**Analysis — D (pagination)**: User has explicitly deferred to MVP. No M2 success criterion (SC-6, SC-7, SC-8 — all dedup quality) requires pagination. The M2 user-observable deliverable (validated dedup + repost indicators on card UI) is fully achievable without pagination. ALIGNED with MVP-M1 deferral.

**Analysis — E (search by title)**: User has explicitly deferred to MVP. No M2 SC requires search. UX-SPEC §6 lists `/` to focus the search input as a keyboard shortcut, but the search box is scoped to the Dismissed tab in §2 ("Search dismissed postings…") not the Main tab card list — search-by-title on Main is a new affordance, appropriately MVP-level. ALIGNED with MVP-M1 deferral.

**Analysis — F (filter by metadata)**: User has explicitly deferred to MVP. PRD §6 Scope OUT names "Soft-rank weight UI sliders, fit-score threshold slider, tag taxonomy editor" as MVP-deferred interactive controls; filter-by-seniority/location/skills is in the same family of interactive query controls. No M2 SC requires it. ALIGNED with MVP-M1 deferral.

**Pattern note**: This is the fourth M2 session in which the user has pushed toward richer UX (role_orientation, LLM-fallback dedup, skills-in-collapsed, now two-pane). Items A+B are low-cost and correctly stay in M2; C is the first architectural UX proposal. No VIOLATES verdict has been issued in M2 — the project is tracking DRIFTING or lower on every boundary test. The user's self-triage on D/E/F demonstrates good scope discipline.

**Recommendation**:
- **A + B**: ALIGNED — add as TASK-M2-015 (template + CSS only, ~half-day). Execute now before M2 closes. A and B are bundled: they constitute a single card layout pass.
- **C**: DRIFTING — recommended landing zone is BACKLOG MVP-M1, bundled with D/E/F. Two-pane, pagination, search, and filter are natural companions in a master-detail layout — plan them together in MVP-M1 where the TDD C9 contract can be revised with full scope. If user overrides: architect must update TDD §1.0 and UX-SPEC §1/§6 before TASK-M2-016 is drafted (keyboard scheme changes, HTMX strategy changes, C9 contract rewrite). Recommend against override — the M2 closure risk is non-trivial and the companion features (D/E/F) make MVP-M1 the cleaner home.
- **D, E, F**: ALIGNED with MVP-M1 deferral (user-confirmed). Add to BACKLOG.md as MVP-M1 items, bundled with C if C is also deferred.

**User decision**: A + B approved (TASK-M2-015 added to M2 scope). C (two-pane) deferred to BACKLOG MVP-M1, bundled with D/E/F. D, E, F deferred to MVP-M1.
**Outcome**: TASK-M2-015 implemented (layout reshuffle + skills moved to collapsed view). Two-pane, pagination, search, filter added to BACKLOG.md as MVP-M1 items. M2 proceeds.

---

## 2026-04-29 — Composite skills-strip redesign: match-against-user-stack + category color + ordering rule + match count footer (TASK-M2-016 proposal)

**Verdict**: ALIGNED
**Mode**: B
**Anchors**:
- PRD §5 Scope IN M2: "LLM extraction call producing `canonical_company / canonical_seniority / canonical_location / team_or_department / top_skills / role_summary` (used here for normalisation only — full classification deferred to M3)" — `top_skills` already exists in `canonical_postings`; this proposal renders it differently, it does not add new extraction fields.
- PRD §4 Phase Objectives: "Each milestone ends with a user-observable web-UI deliverable on real data."
- PRD §5 Scope IN M2 (M2 end-state deliverable): the card UI is the M2 user-observable surface; TASK-M2-014 (ALIGNED, 2026-04-29) and TASK-M2-015 (Done, `4cb7a36`) established that display-policy decisions over already-extracted fields are M2-in-scope as long as no new schema columns, extraction calls, or probabilistic components are introduced.
- ALIGNMENT-LOG 2026-04-29 — "Surface M2-available LLM fields in collapsed card" (ALIGNED): "All four already exist in `canonical_postings` — zero new extraction, zero new schema columns, zero probabilistic components."
- PRD §3 Commercial Thesis — Hedge 4 (Taxonomy portability): "Classification prompt and tag taxonomy written in role-family-generic language." — `config/skill_categories.yaml` (a universal skill→category mapping) is a portable config artifact in the same family as the tag taxonomy. It strengthens, not weakens, the canonical taxonomy as differentiator.
- ROADMAP.md M3 scope: "Single LLM extraction prompt... producing all of: canonical fields + salary + tags + `primary_focus` + `fit_score` + `fit_reasoning` + `requires_pr_or_citizenship`" — CV-driven role-fit scoring is M3's job. `config/user_profile.yaml` + match-against-user-stack is NOT this: it is a static config lookup (list membership check), not an LLM scoring call, not a vector similarity computation, and not a CV-embedding-based recommender (which is M4).
- PRD §5 Scope IN M4: "CV text extraction... cosine rank against `role_summary + top_skills` embedding" — the M4 CV recommender is embedding-based cosine similarity against extracted CV text. Match-against-user-stack is a set-intersection on a manually curated YAML list. These are categorically different mechanisms.
- ROADMAP.md M3 deliverable: "Cards arrive pre-classified, pre-scored, pre-filtered." The composite design produces no score and no filter — it is a read-only rendering decision on data already in the DB.
- PRD §6 Scope OUT: no clause prohibits a config file listing the user's known skills, category-color chip rendering, or a chip-count footer.

**Analysis**: The composite design touches three artifacts — two new config files (`user_profile.yaml`, `skill_categories.yaml`) and a rendering update to `_card.html`/CSS/`canonical_view.py`. None of these introduce a new database column, a new LLM call, a new embedding computation, or a new probabilistic component. The match-against-user-stack logic is a set-intersection between `top_skills` (already extracted and stored) and a static YAML list; it is structurally identical to a config-driven filter and has no dependency on M3's LLM classification pass or M4's CV-embedding pipeline. The M3 CV-fit boundary is clear: M3 adds LLM-extracted `fit_score`/`fit_reasoning`/`primary_focus` via a cloud prompt call — none of that is present here. M4 adds cosine similarity against CV embeddings — also absent here. Match-against-user-stack is a presentational heuristic, not a fit-scoring engine; it makes existing `top_skills` data more readable without computing anything that M3/M4 would compute differently. The `user_profile.yaml` file does not couple to M3 work — it is not consumed by the M3 LLM prompt, it is not an input to M4's CV recommender, and its presence does not foreclose any M3/M4 design decision. If anything, shipping it early validates whether a curated static list is useful, which is useful signal before M3's richer scoring arrives. Commercial signal: `skill_categories.yaml` is an extension of Hedge 4 (taxonomy portability) — a reusable, role-family-generic skill taxonomy is exactly the kind of differentiated config asset the commercial thesis names as portable to other technical personas at Beta. The composite design strengthens it.

Pattern note from prior log: three M2 proposals expanded the LLM layer beyond normalisation (role_orientation DRIFTING/deferred; LLM dedup gatekeeper DRIFTING/promoted to TASK-M2-012; six UX proposals batch had two-pane DRIFTING/deferred). This proposal does NOT expand the LLM layer at all — it is a pure rendering change on existing data. The pattern of enrichment pressure in M2 is real, but this specific proposal is qualitatively different: no new LLM scope, no new schema, no probabilistic component. Scope-creep risk: approving TASK-M2-016 does not open the door to additional UX polish — it is a bounded, well-specified task (two config files + template + CSS + ~10-12 tests). The "add more UX polish" risk is contained by the fact that M2's remaining open task is TASK-M2-012 (real-data validation + threshold calibration), which is functional validation work. Any further UX proposal after M2-016 should go through BA before entering M2 scope.

**Recommendation**: ALIGNED — add as TASK-M2-016. Ask user: "Proceed now or park for after TASK-M2-012?"

**M3 CV-fit boundary note** (specific answer to the concern raised): Match-against-user-stack ends at the chip-rendering layer. It reads `top_skills` from `canonical_postings`, intersects with a static YAML list, and emits a render-payload. It produces no score column, no DB write beyond the existing schema, and no input to the M3 LLM prompt. M3 CV-fit begins when the LLM prompt receives a job description and outputs `fit_score`/`fit_reasoning` — a generative scoring step that reasons over the full JD. M4 CV-fit begins when CV embeddings are compared to role_summary+top_skills via cosine similarity. The three mechanisms are non-overlapping and non-competing: `user_profile.yaml` does not anchor, constrain, or conflict with the M3 or M4 implementation. There is no coupling risk.

**User decision**: Approved (TASK-M2-016 added to M2 scope — completed 2026-04-29, commit 7ea5674)
**Outcome**: TASK-M2-016 implemented: skills tiering with match-against-user-stack, category color coding (4 buckets: DS/ML purple, Languages blue, Platforms/Tools green, Other gray), ordering rule (matching first by category priority), and `Skills match: X/Y` footer. Two new config files: `config/user_profile.yaml` (31-entry core_skills list) and `config/skill_categories.yaml` (alias map included). 905 tests passing. Committed and pushed.

---

## 2026-04-29 — M2 closure: Content-aware dedup + repost detection + UX enrichment (all 16 tasks Done)

**Verdict**: ALIGNED
**Mode**: B
**Anchors**:
- PRD §5 Scope IN M2: "LLM extraction call producing `canonical_company / canonical_seniority / canonical_location / team_or_department / top_skills / role_summary` (used here for normalisation only — full classification deferred to M3)"
- PRD §5 Scope IN M2: "Two-stage dedup: block by `(canonical_company, canonical_seniority, canonical_location)`; fuse cosine + structured similarity at 50/50"
- PRD §5 Scope IN M2: "Repost detection (same JD, new jobId, 30+ days later — threshold config-driven, default 30)"
- PRD §7 Success Criteria SC-6: "Content-aware dedup overall — ≥90% on 30 hand-labeled pairs — M2"
- PRD §7 Success Criteria SC-7: "Content-aware dedup — different-team false-merge rate — ZERO — regression-blocking — M2"
- PRD §7 Success Criteria SC-8: "Cross-source merge — Verified — synthetic cross-source pairs acceptable where live Indeed unavailable per PRD §9 R3 — M2"
- PRD §3 Commercial Thesis: five architectural hedges (namespace-aware schema, events instrumentation, taxonomy portability, classify-always, open-source) — all intact at M2 closure.
- PRD §9 R3: "Realized 2026-04-28 at PoC M2: IP-level Cloudflare enforcement on user's employer-managed Mac. Indeed extraction deferred to MVP-M1." (Override BA accepted 2026-04-28)

**Analysis**: All 16 M2 tasks Done; all 6 ROADMAP §M2 ACs pass. SC-6 exceeded: gatekeeper-augmented P=1.000, R=0.857, F1=0.923 on 15 real-data labeled pairs. SC-7 holds at ZERO different-team false-merges (regression-blocking). SC-8 satisfied via synthetic cross-source fixtures per PRD §9 R3 revised scope. PRD §3 Commercial Thesis is strengthened: the canonical-taxonomy + dedup-quality differentiator is now backed by empirical evidence — calibrated FUSE engine + LLM gatekeeper demonstrating zero different-team false-merges. Hedge 4 (taxonomy portability) is actively extended by `skill_categories.yaml`. No PRD §6 Scope OUT clause was breached. Beta gates are untouched.

**Significant scope additions during M2 and their alignment status:**

1. **TASK-M2-012 — LLM dedup gatekeeper (BACKLOG promotion)**: Originally proposed as DRIFTING (LLM-fallback for borderline pairs); user accepted BA recommendation to defer decision to M2-012 calibration. Calibration data (fuzzy-zone hit rate on 30-pair set) supported promoting the gatekeeper into M2-012 scope. Provider-abstracted (C28), cost-metered, fail-CLOSED. Not a scope violation — a data-driven promotion through the prescribed calibration gate (PRD §10 Open Question #4).

2. **TASKS-M2-014/015/016 — Card UI enrichment, layout reshuffle, skills tiering**: All three ALIGNED at verdict. Pure display-policy decisions over already-extracted `canonical_postings` fields — zero new schema columns, zero new LLM calls, zero probabilistic components. Consistent with PRD §4 Phase Objectives (user-observable deliverable per milestone). The two-pane layout (DRIFTING) was correctly parked to MVP-M1; user self-triaged pagination/search/filter to MVP-M1 as well.

3. **Tab-count badges fix (surfaced during TASK-M2-013 demo)**: Bug-fix-forward — tab counters not live-updating after apply/dismiss. Corrected as minor fix within the demo task. No scope implications.

**Pattern note**: Four DRIFTING verdicts in M2, zero VIOLATES. The user's pressure toward richer LLM extraction and UX was real but routed through Gate 2 each time. The calibration-first containment valve held. Self-triage of D/E/F (pagination, search, filter) to MVP-M1 demonstrates scope discipline at the boundary that matters commercially.

**Recommendation**: Proceed to M3 (Smart layer — fit_score / primary_focus / classification / PR filter). No signal for premature phase transition. M3 and M4 are required to satisfy PoC exit criteria 1 (all four components meet thresholds) and 2 (end-to-end on real data through M4). BACKLOG items ripe for M3 input: taxonomy expansion (tail-skill additions), `role_orientation` classification field, staffing-firm repost recognition.

**User decision**: M2 approved (explicit "approve" 2026-04-29).
**Outcome**: M2 formally closed 2026-04-29. All 16 tasks Done; all 6 ROADMAP §M2 ACs PASS; user-approved verbatim. PoC phase continues — next: /milestone-plan jd-matcher for Milestone 3 (Smart layer).
