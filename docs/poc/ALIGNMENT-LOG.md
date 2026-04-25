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
- **User decision**: [To be filled after user reviews]
- **Outcome**: [To be filled after user reviews]
