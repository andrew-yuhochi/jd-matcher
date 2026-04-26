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
