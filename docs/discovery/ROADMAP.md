# Roadmap — jd-matcher

> **Status**: Draft
> **Author**: architect
> **Last Updated**: 2026-04-24
> **Approved by user**: [ ] Pending

---

## Framing

User is actively job-hunting; urgency is the dominant constraint. PoC milestones are sequenced so that **M1 produces a usable daily output (raw fresh job list in the browser) within roughly one week** — every milestone after that adds intelligence on top of an already-running pipeline. Personal-first throughout PoC and MVP. Commercial optionality is hedged inside PoC (see "Cross-Cutting Commercial Hedges" below) but not pursued until the Beta decision gate. See DISCOVERY-NOTES.md §11 (urgency) and §13 (positioning).

---

## Phase Overview

| Phase | Status | Scope (one line) | Exit Criteria (one line) |
|-------|--------|------------------|--------------------------|
| Discovery | Complete | Requirements locked, ingestion architecture validated, UX designed, market thesis written | This ROADMAP user-approved |
| PoC | Active next | Build + validate the four critical components against hand-labeled samples; one-shot daily-use surface | All four components meet quality bars; user runs full flow end-to-end on real data and approves Milestone 4 deliverable |
| MVP | After PoC | Run unattended daily for 4-8 weeks; reliability hardening; coverage expansion based on PoC gaps; dismissal-learning + analytics surface | 28 consecutive days of unattended runs without manual intervention; analytics show ≤5 min/day median triage time; user approves stability for ongoing personal use |
| Beta | Decision gate | Variant A "stay personal" — durability hardening only. Variant B "go commercial" — multi-tenant rewrite + LinkedIn ingestion overhaul + benchmark extension. **Decision triggered by passing all three Beta gates from MARKET-ANALYSIS.md** | Variant A: 6 months stable personal use. Variant B: open-source release with managed-tier signups, ToS-clean ingestion path, ≥3 articulated paying personas |

---

## PoC

### Scope

Validate the four capabilities that determine whether the rest of the system can be trusted:
1. Multi-source ingestion (Gmail-driven LinkedIn/Indeed/Job Bank email parsing + JD hydration; direct API polling for Himalayas/Remotive/Jobicy/HN). *Indeed deferred to MVP at 2026-04-28 — see PRD §9 R3 realized risk.*
2. Content-aware deduplication (LLM-extracted fields + embedding similarity, two-stage)
3. LLM single-call extraction + classification + role-fit scoring
4. CV-to-posting recommender (cosine on embeddings)

PoC delivers a working local web app on `localhost:PORT` with the three views (Main / Applied / Dismissed) defined in UX-SPEC.md. Pipeline is run on demand and on a basic local schedule. Single user, SQLite, FastAPI, cloud LLM by default (OpenAI `gpt-4o-mini` for extraction, `text-embedding-3-small` for embeddings) — chosen to avoid multi-GB local model downloads multiplying across the portfolio. Local Ollama (`qwen2.5:7b`) and local sentence-transformers remain config-swappable optional fallbacks. Combined PoC LLM cost: ~$0.65/month at 20 postings/day.

### Critical components to validate

Per DISCOVERY-NOTES.md §5, §6, §7 — quality bars are the published Gate 4 standards.

| # | Component | Capability to prove | Minimum threshold | Validated in |
|---|-----------|---------------------|------------------|--------------|
| 1 | Ingestion + JD hydration | URL extraction from LinkedIn/Indeed alert emails; full-JD hydration via guest endpoints; structured API calls to Himalayas/Remotive/Jobicy/HN succeed | LinkedIn/Indeed: ≥95% URL extraction on ≥50 sample emails (M1 PASSED for both; Indeed paused for live ingest at M2 per PRD §9 R3). JD hydration: ≥95% successful full-JD fetch (≥30 samples). API sources: ≥95% successful structured fetch (deterministic). | M1, M4 |
| 2 | Content-aware dedup | Same-job/different-source merges; same-title/different-team postings stay separate | ≥90% accuracy on 30 hand-labeled pairs (10 dup, 10 non-dup, 10 ambiguous); **zero false-merges** on different-team cases | M2 |
| 3 | LLM extraction + classify + fit | One prompt extracts canonical fields, salary, tags, fit score | `primary_focus` agreement ≥80%; multi-tag Jaccard ≥70%; `fit_score` accept/reject agreement ≥90% at threshold 50; salary extraction ≥90% (probabilistic — user approval gate) | M3 |
| 4 | CV recommender | Top-1 CV match aligns with user's manual choice | ≥80% top-1 agreement on 20 hand-labeled postings (probabilistic — user approval gate) | M4 |

### Out of scope (PoC)

- Push notifications or mobile (UX-SPEC.md "What NOT to Build")
- LLM CV rewriting, auto-apply (DISCOVERY-NOTES.md §14)
- Multi-tenant infrastructure beyond the namespace-aware schema hedge (DISCOVERY-NOTES.md §10.5 hedge 3)
- French-language postings (DISCOVERY-NOTES.md §14)
- Cross-location merge pass, "possible duplicate" UI hint (DISCOVERY-NOTES.md §5)
- Soft-rank weight UI, threshold sliders, taxonomy editor (UX-SPEC.md §9 — MVP)
- Dismissal-learning loop (DISCOVERY-NOTES.md §6 — MVP)
- Greenhouse/Lever ATS sources, Google for Jobs, Monster, Wellfound (DISCOVERY-NOTES.md §3, §14)
- Cron / launchd full automation (basic schedule only — full automation in MVP)

### Exit criteria (PoC)

All of the following must be true:

1. All four critical components meet thresholds in their validation milestones.
2. User has run the end-to-end flow on real data through M4 and approved the deliverable.
3. ≥30-pair dedup hand-label, ≥30 LLM-extraction hand-label, ≥20 CV-recommender hand-label, all stored in `quality-logs/`.
4. Time-savings instrumentation captures session events; analytics page shows at least one full triage session end-to-end.
5. PHASE-REVIEW.md produced and user-approved.

---

### PoC Milestone Decomposition

Four milestones. Each ends with a user-observable web-UI deliverable that the user can interact with on real data.

#### Milestone 1 — Raw pipe + URL dedup + applied/dismissed state (week 1 + ~1 day)

| Field | Value |
|-------|-------|
| **Goal** | Get fresh LinkedIn + Indeed jobs from Gmail into a browser within a week, with day-one URL-based dedup and applied/dismissed state so the same posting never reappears across daily runs. First useful day of jd-matcher — supports the "clear in under a minute" workflow from session one. |
| **User-observable deliverable** | Open `localhost:PORT`, see a stack of new postings from today's LinkedIn + Indeed emails with title/company/location/URL/source. Click a card → expand → click apply URL → goes to LinkedIn/Indeed. Click `[Mark Applied]` → posting moves to Applied tab. Click `[Dismiss]` → posting moves to Dismissed tab and is permanently blacklisted. Re-run pipeline → same URLs ingested today no longer appear in Main, and applied/dismissed postings stay out of Main. No content-aware dedup, no fit score, no tags yet. |
| **Critical components built** | Gmail OAuth loopback flow; LinkedIn email parser (URL regex on plain-text part); Indeed email parser; JD hydration via LinkedIn/Indeed guest endpoints (rate-limited, 1 req/30s); SQLite schema (with `user_id` namespace + `events` table — hedges 2 & 3); `seen_urls` table + URL-based dedup check on ingest; `applied` and `dismissed` state tables (namespaced); state-aware Main view query (excludes URLs already in applied/dismissed); FastAPI app skeleton; Main / Applied / Dismissed tabs rendering postings per UX-SPEC.md §2; `[Mark Applied]` and `[Dismiss]` buttons with persistent state; basic `/pipeline/run` endpoint; public GitHub repo with README + MIT LICENSE (hedge 5). |
| **Acceptance criteria** | (1) Gmail OAuth completes one-time setup; refresh-token reuse on subsequent runs proven. (2) ≥95% URL extraction success on ≥50 historical LinkedIn alert emails; ≥95% on ≥30 historical Indeed emails. (3) ≥95% successful JD hydration on ≥30 sample URLs (deterministic — bug if not). (4) Web UI shows ≥20 postings rendered correctly per UX-SPEC.md collapsed-card spec across Main / Applied / Dismissed tabs. (5) URL-based dedup: re-running pipeline against the same Gmail inbox does NOT re-add postings whose URLs are already in `seen_urls` (verified end-to-end). (6) Mark Applied → posting appears in Applied tab and is removed from Main; persists across server restart. (7) Dismiss → posting appears in Dismissed tab and is permanently blacklisted (never resurfaces in Main even on re-ingest); persists across server restart. (8) `events` table records `card_viewed`, `card_dismissed`, and `card_marked_applied` events with timestamps (hedge 2). (9) Repo public on `github.com/andrew-yuhochi/jd-matcher` with README "Built with Claude Code" badge. |
| **Quality bar** | Deterministic components — Gate 4 ≥95% pass rate, root-cause-first on failures, up to 3 auto-fix attempts. ≥30 sample minimum for URL extraction and hydration. URL-dedup and state persistence are deterministic — must be 100%. |
| **Dependencies** | None — first milestone. User must set up LinkedIn (7 saved searches per DISCOVERY-NOTES.md §4), Indeed (2-3 alerts), and Gmail filtering label before this milestone runs. |

#### Milestone 2 — Content-aware dedup + repost detection (week 2)

| Field | Value |
|-------|-------|
| **Goal** | Same job posted to LinkedIn AND Indeed (different URLs, different `jobId`s) is recognized as a single canonical posting. Reposts of the same JD under a fresh `jobId` after 30+ days are recognized as the same role. Generalizes M1's URL-based dedup into content-based recognition. |
| **User-observable deliverable** | Same web app as M1, but now: (a) duplicate postings across LinkedIn (and other sources where active in PoC) are visibly merged into a single card with multiple `Sources:` listed. *Indeed and Himalayas deferred to MVP-M1 / M4 respectively; cross-source dedup mechanism validated via synthetic fixtures per revised SC-8.* (b) when one variant is dismissed or applied, the canonical record's state suppresses all matched variants from Main on subsequent runs (state inherited from M1, now keyed off canonical-id rather than just URL); (c) reposted JDs surface as a single card with original `first_seen` preserved. |
| **Critical components built** | LLM extraction call producing `canonical_company / canonical_seniority / canonical_location / team_or_department / top_skills / role_summary` (used here for normalization only — full classification deferred to M3); `text-embedding-3-small` cloud embedding pipeline (config-swappable to local `all-MiniLM-L6-v2`); two-stage dedup (block by `(company, seniority, location)`, fuse embedding cosine + structured similarity 50/50); canonical-record merge logic preserving `first_seen` + `sources[]`; cross-state dedup check generalized to canonical-id (new posting matching applied/dismissed canonical → suppressed, building on M1's URL-keyed state tables); repost detection (same JD, new `jobId`, 30+ days later); Himalayas API source. |
| **Acceptance criteria** | (1) ≥90% accuracy on 30 hand-labeled posting pairs (10 dup / 10 non-dup / 10 ambiguous). (2) **Zero false-merges** on the 10 different-team cases (regression-blocking). (3) Cross-source merge mechanism: ≥3 verified cross-source pairs collapse to one card (synthetic acceptable per revised SC-8 / PRD §9 R3 — live Indeed unavailable due to Cloudflare IP-level enforcement on user's hardware). The C21 dedup mechanism is the validation target. (4) State inheritance generalizes from M1: dismissing one source's variant suppresses the canonical record across all sources on the next run. (5) Repost detection: same JD with new `jobId` after 30+ days → merged with preserved `first_seen` (verified on ≥3 real cases or synthetic). (6) Auto-merge threshold 0.90 calibrated against the hand-labeled set, recorded in config. |
| **Quality bar** | Content-aware dedup is deterministic-with-LLM-inputs — Gate 4 ≥95% pass on clear cases, **0 false-merges** on different-team cases. Probabilistic LLM extraction quality is checked here for normalization only; full extraction-quality validation is M3. |
| **Dependencies** | M1 (URL-dedup foundation, applied/dismissed state, ingestion pipe — all generalized here from URL-keyed to canonical-id-keyed). |

#### Milestone 3 — Smart layer (week 3)

| Field | Value |
|-------|-------|
| **Goal** | Cards arrive pre-classified, pre-scored, pre-filtered. User opens app and immediately sees a sorted shortlist with tags and salary. |
| **User-observable deliverable** | Web app now shows: primary tag chip (coloured per UX-SPEC.md §6 palette), secondary tags in expanded view, salary range, fit score driving the visible shortlist (default `fit_threshold: 50`), soft-rank ordering by salary + industry + recency. Below-threshold postings remain in the database (queryable, hedge 1) but hidden from Main view. Taxonomy review pass: after ~100 classified postings, rename/merge/split tags. |
| **Critical components built** | Single LLM extraction prompt (cloud-default OpenAI `gpt-4o-mini`, ~$0.60/month at 20 postings/day; config-swappable to local Ollama `qwen2.5:7b` if user later prefers local) producing all of: canonical fields + salary + tags + primary_focus + fit_score + fit_reasoning + requires_pr_or_citizenship; hard-filter pre-LLM keyword list for PR/citizenship (DISCOVERY-NOTES.md §6 Layer 1); soft-rank composite scoring; Main view sort + filter (view policy, hedge 1); taxonomy revision pass; full classification persisted on every posting regardless of filter outcome (hedge 1); generic role-family-language prompt (hedge 4). **Optional**: local-vs-cloud benchmark sub-task (Ollama `qwen2.5:7b` vs `gpt-4o-mini` on the hand-labeled set) — runs only if user explicitly opts in; not a default M3 deliverable. |
| **Acceptance criteria** | (1) `primary_focus` ≥80% agreement with user labels on ≥30 hand-labeled postings using cloud `gpt-4o-mini`. (2) Multi-tag Jaccard ≥70%. (3) `fit_score` ≥90% accept/reject agreement at threshold 50. (4) Salary extraction ≥90% within ±10% on the labeled subset where salary is stated. (5) Hard-filter Layer 1 rejects all 10 PR/citizenship-required test cases (zero false-negatives — different-team principle equivalent here: don't surface ineligible roles). (6) Below-threshold postings count visible in events/admin view (proves hedge 1 works). (7) Cloud-LLM cost report: actual `gpt-4o-mini` extraction cost over the milestone window logged to `quality-logs/llm-cost.md`; expected ≤$1/month. (8) Taxonomy revision: tag distribution after 100 postings recorded; ≥1 rename/merge/split applied based on real data, recorded in config. (9) **User approves probabilistic outputs** before milestone closes. (10) **Optional, only if opted in**: local-vs-cloud benchmark report in `quality-logs/llm-benchmark.md`. |
| **Quality bar** | Probabilistic — fit_score and tag classification flagged for user approval per Gate 4. Salary extraction has both a deterministic threshold (≥90% within ±10%) and user review of the failure cases. Validation is against cloud `gpt-4o-mini` extraction quality on the hand-labeled sample. |
| **Dependencies** | M2 (postings must already be deduplicated; LLM call should run on canonical records, not raw postings). |

#### Milestone 4 — CV recommender + extended sources (week 4)

| Field | Value |
|-------|-------|
| **Goal** | User sees a CV recommendation per posting and can override. Coverage expands from LinkedIn (Indeed deferred to MVP-M1) to also include Job Bank Canada, Remotive, Jobicy, HN. Settings page exists. Time-savings analytics view exists. |
| **User-observable deliverable** | Cards now show `CV: CV-LLM.pdf  ← highest cosine match (RAG + agents focus)` per UX-SPEC.md §5; expanded-card override dropdown lists all 5 CVs ranked by score; `c` key copies recommended CV filename. `/settings` page accepts 5 CV filesystem paths. New sources: Job Bank Canada (email), Remotive (API), Jobicy (API), HN Hiring (RSS). Analytics view at `/analytics` shows session events: median time-per-card, sessions per day, time-to-clear-inbox, dismiss/apply ratio (hedge 2 surface). |
| **Critical components built** | CV-text extraction (PyMuPDF or pdfplumber) at startup; CV-embedding pipeline (same `text-embedding-3-small` cloud model used in M2 for parity; config-swappable to local `all-MiniLM-L6-v2`); cosine-rank against `role_summary + top_skills` embedding; top-1 + override storage; Settings page (Gmail status, 5 CV path inputs, last-pipeline-run readout per UX-SPEC.md §9 PoC scope); Job Bank Canada email parser; Remotive API client (`category=ai-ml`); Jobicy API client (`geo=canada`); HN HNRSS regex parser; analytics view rendering events-table aggregations; coverage gap audit task (record sources/queries adding postings the others missed). |
| **Acceptance criteria** | (1) ≥80% top-1 agreement with user's CV choice on 20 hand-labeled postings (probabilistic — user approval gate). (2) Override dropdown saves and persists CV choice per posting across server restarts. (3) All four new sources successfully ingest ≥1 real posting each (deterministic). (4) Job Bank parser works on ≥10 real Job Bank emails with ≥90% URL extraction (Risk 3 from RESEARCH-REPORT.md §8 — fragile, validate explicitly). (5) Settings page edits persist to config. (6) `/analytics` shows ≥1 full session end-to-end (open → triage all → close) with measured `time_to_clear` (hedge 2 deliverable). (7) Coverage audit report: which sources contributed unique postings during the milestone window (Beta Gate 2 input data). (8) **User approves the CV recommendation samples** before milestone closes. |
| **Quality bar** | CV recommender is probabilistic — user approval gate. Source ingestions are deterministic — ≥95% structural success. Job Bank parser is fragile (Risk 3); a ≥90% bar is acceptable for PoC, with a known fallback to direct scraping if it falls below in MVP. |
| **Dependencies** | M3 (LLM extraction outputs `top_skills` and `role_summary` which the CV recommender embeds against). |

---

## Cross-Cutting Commercial Hedges (PoC)

Per DISCOVERY-NOTES.md §10.5 these are NOT standalone milestones. They are threaded through milestone acceptance criteria above. Architect verifies each in PHASE-REVIEW.

| # | Hedge | Threaded into |
|---|-------|---------------|
| 1 | Classify always, filter configurably | M3 AC #6 — below-threshold postings remain queryable; filtering is a view policy. |
| 2 | Time-savings instrumentation | M1 AC #8 (events table records `card_viewed`, `card_dismissed`, `card_marked_applied`), M4 AC #6 (analytics view rendering events). |
| 3 | Namespace-aware data model | M1 — every table created (postings, `seen_urls`, `applied`, `dismissed`, `events`) has a `user_id` column defaulted to `'default'`, queries filter by it. |
| 4 | Taxonomy portability | M3 AC #8 — prompt phrased in role-family-generic language, taxonomy revisable in config. |
| 5 | Open-source from day 1 | M1 AC #9 — public GitHub repo + MIT LICENSE + README from first task. |

**Deferred to pre-Beta** (DISCOVERY-NOTES.md §10.5): hand-labeled benchmark extension from 30 → 100. Performed only if Beta Variant B (commercial) is being explored.

---

## MVP

### Scope

The PoC proves the components work in isolation against hand-labeled samples. MVP proves the system **runs unattended for weeks of real daily use**. Reliability hardening, scheduling, coverage expansion based on PoC gaps, and dismissal-learning + threshold-tuning surfaces are added. UX polish based on real-use feedback. The user uses jd-matcher as their primary daily job-search tool throughout MVP.

### MVP Milestones

#### MVP-M1 — Unattended automation + reliability

| Field | Value |
|-------|-------|
| **Goal** | The pipeline runs hourly via launchd without user intervention. Gmail OAuth refresh handled gracefully. Per-source failures don't break the run. |
| **User-observable deliverable** | User does not run `[Run sync now]` for a week — postings appear automatically. Sub-bar shows "Last sync: 12 min ago" reliably. Banner appears if Gmail token expires (UX-SPEC.md §8). |
| **Critical components built** | launchd plist (macOS) installer; Gmail token-refresh handling with explicit re-auth prompt; per-source try/except with logged failures (no one source kills the run); per-source freshness indicator on `last sync` timestamp tooltip (UX-SPEC.md §8); structured logging with rotation. |
| **Acceptance criteria** | 14 consecutive days of unattended runs with no manual intervention; Gmail token refresh proven on at least one cycle; one source intentionally broken → other sources still ingest; logs reviewable post-hoc. |

#### MVP-M2 — Coverage expansion + French + dismissal-learning

| Field | Value |
|-------|-------|
| **Goal** | Address coverage gaps surfaced during real PoC use; add French; dismissal becomes a feedback signal. |
| **User-observable deliverable** | (a) Additional sources or LinkedIn search keywords added based on PoC M4 coverage audit (e.g. `AI Engineer`, `Applied AI Research`, possibly Greenhouse curated list per RESEARCH-REPORT.md §5); (b) French postings ingested + classified; (c) dismissal-reason categories on `[Dismiss]` flow; (d) weekly review surface that proposes threshold and keyword-list adjustments based on dismissals. |
| **Critical components built** | Greenhouse ATS API client + curated employer slug list (if PoC coverage audit indicates gap); French-capable embedding model swap (e.g. `paraphrase-multilingual-MiniLM-L12-v2`); dismissal-reason taxonomy + UI dropdown; weekly review job that aggregates dismissal reasons and surfaces tuning recommendations. |
| **Acceptance criteria** | New coverage source contributes ≥3 unique postings/week not from existing sources; ≥90% French URL+title extraction on ≥20 French samples; dismissal-reason captured on ≥80% of dismiss actions; weekly review surface produces actionable recommendations on real dismissal data. |

#### MVP-M3 — UX polish + settings expansion

| Field | Value |
|-------|-------|
| **Goal** | Daily-use friction discovered during PoC and MVP-M1 is resolved. Settings page covers tunable knobs. |
| **User-observable deliverable** | Settings page expands to UX-SPEC.md §9 "MVP additions": soft-rank weight sliders, fit-score threshold slider with live preview count, tag taxonomy editor. UX-friction items from real use addressed (e.g. open UX questions resolved, keyboard-shortcut refinements, two-column option if requested). |
| **Critical components built** | Settings page expansion; live-preview query against the database; taxonomy editor with rename/merge/add (with reclassification trigger or "stale-tag" indicator); UX adjustments per real-use feedback. |
| **Acceptance criteria** | All open UX questions from UX-SPEC.md §"Open UX Questions" resolved with documented decisions; settings changes persist and take effect; ≥1 taxonomy edit performed live and reflected in classifications. |

### Out of scope (MVP)

- Multi-tenant infrastructure (Beta Variant B only)
- Authentication / user accounts (Beta Variant B only)
- Cloud hosting (Beta Variant B only)
- LinkedIn ingestion overhaul (Beta Variant B only — see DISCOVERY-NOTES.md §10.5 commercial wall)
- LLM CV rewriting, auto-apply (DISCOVERY-NOTES.md §14 — permanent)
- Mobile app, push notifications (DISCOVERY-NOTES.md §14 — permanent)

### Exit criteria (MVP)

1. 28 consecutive days of unattended pipeline runs with zero manual intervention.
2. Median triage time per session ≤5 minutes (Beta Gate 1 input — measured from analytics view).
3. Coverage audit shows ≥3 unique postings per week from non-LinkedIn sources (Beta Gate 2 input).
4. ≥80% top-1 CV recommender agreement on a fresh ≥20-posting sample from MVP traffic (no regression from PoC).
5. User has used the tool through ≥4 weeks of active job search and confirms it is durable for ongoing use.
6. PHASE-REVIEW.md produced and user-approved.
7. **Beta gate evaluation completed**: user, with market-analyst, formally evaluates Beta Gates 1-3 from MARKET-ANALYSIS.md and chooses Variant A or Variant B.

---

## Beta — Decision Gate

Beta kickoff is **a user decision**, not a default progression. At the end of MVP, user evaluates the three Beta gates from MARKET-ANALYSIS.md:

| Gate | Condition | Source of evidence |
|------|-----------|-------------------|
| Gate 1 — Time savings | ≤5 min/day median triage on ≥80% of days over a 3-week window | Analytics view (hedge 2 instrumentation) |
| Gate 2 — Coverage superiority | ≥3 relevant postings/week from non-LinkedIn sources over the MVP window | M4 + MVP coverage audit |
| Gate 3 — Generalizable personas | User can name ≥2 reachable communities outside DS who share the same pain | User reflection + market-analyst review |

**All three pass → Variant B candidate.** Spawn `market-analyst` for a 2-week commercial spike before committing.
**Any gate fails → Variant A.** Stay personal.

### Variant A — Stay personal (default)

#### Scope

Limited-scope durability hardening. The tool already works; Beta-A is about making it last for years of intermittent personal use without rot.

#### Beta-A milestones

- **A1 — Multi-year durability**: refactor source parsers to fail gracefully on template changes (URL-only fallback for LinkedIn/Indeed); Gmail OAuth re-auth UX hardened; SQLite migration scripts for schema evolution; backup/restore for applied+dismissed state.
- **A2 — Maintenance ease**: documented runbook for adding a new source; documented procedure for taxonomy revision; CI on the dedup hand-labeled set so regressions are caught.

#### Exit criteria (Variant A)

1. Tool runs through ≥1 LinkedIn email template change with ≤1 day of downtime (URL-only fallback proven).
2. ≥6 months of unattended use after Beta-A close with no architectural rework needed.
3. Documentation sufficient for the user to add a source or revise taxonomy without re-reading the codebase.

### Variant B — Go commercial

#### Scope

Pivot phase. The personal tool becomes the foundation; commercial-grade infrastructure is built around it. Multi-tenant rewrite, ingestion overhaul (the LinkedIn guest-endpoint approach does not scale commercially — see MARKET-ANALYSIS.md Risk 1 / DISCOVERY-NOTES.md §10.5 commercial wall), benchmark extension, and open-source-with-managed-tier distribution per MARKET-ANALYSIS.md Recommendation 2.

#### Beta-B milestones

- **B1 — Hand-labeled benchmark extension**: 30 → 100 labeled postings (DISCOVERY-NOTES.md §10.5 deferred item).
- **B2 — Multi-tenant rewrite**: PostgreSQL + per-tenant namespacing (additive on the hedge-3 schema), authentication, per-user CV vault, per-user OAuth.
- **B3 — Ingestion overhaul**: LinkedIn guest-endpoint dropped; replaced with email-only-at-scale or paid aggregator (e.g. SerpAPI Starter at $25/mo, or licensed feed); ToS-clean architecture documented.
- **B4 — Distribution**: open-source release on GitHub (already there from hedge 5), README + docs polished, managed-tier signup landing page, CAC < $60 acquisition target per MARKET-ANALYSIS.md Path A.

#### Exit criteria (Variant B)

1. ≥3 articulable paying personas with at least one reachable community per persona.
2. Multi-tenant deployment serving ≥3 external users (friend-of-friend / community pilot).
3. ToS-clean ingestion path live for all sources (no guest-endpoint scraping at commercial volume).
4. ≥80% accuracy maintained on the extended 100-posting benchmark.
5. ≥1 paying conversion from the managed tier OR ≥500 GitHub stars (Path C signal).

---

## Risks and Mitigations

| # | Risk | Severity | Mitigation |
|---|------|----------|------------|
| R1 | LinkedIn alert email template change silently breaks parser | High | Build URL-extraction-first parser (RESEARCH-REPORT.md §3); URL regex stable across template redesigns; emit health metric "URL-only fraction" — alert if >20%; store raw email bodies for replay against new parser. |
| R2 | Gmail OAuth refresh token revoked (90+ days inactive, app in Testing status, or user revokes) | Medium | Startup health check before pipeline run; clear "Re-run auth flow" error message; document in README; banner per UX-SPEC.md §8. |
| R3 | LinkedIn / Indeed rate-limit or IP-block at JD hydration step | Medium | 1 req/30s rate limit baked in (DISCOVERY-NOTES.md §3); ~40 hydrations/day total — indistinguishable from human; degrade gracefully (store URL even if hydration fails); fall back to email-teaser for that posting until next retry. |
| R4 | User's LinkedIn saved searches too narrow → coverage gap | Medium | M4 coverage audit explicitly tracks unique-source contributions; MVP-M2 expands keywords based on audit findings; DISCOVERY-NOTES.md §4 lists candidate expansions. |
| R5 | LLM classifier drift over time (model update, prompt staleness) | Medium | Hand-labeled benchmark stored permanently; quarterly re-evaluation against same set during MVP; benchmark extension to 100 at Beta-B. |
| R6 | Taxonomy revision invalidates prior classifications | Medium | M3 taxonomy revision is one-shot during PoC; MVP-M3 taxonomy editor flags affected postings as "stale-tag" rather than silently discarding; reclassification can be triggered manually. |
| R7 | User's Open Work Permit status changes (PR granted, OWP expires) | Low (context, not technical) | Hard-filter rules are config-driven (`filter.pr_keyword_list`, location list) — config edit, not code change; documented in CLAUDE.md per-project. |
| R8 | Job Bank Canada email parser fails (gov't IT cycle changes template) | Medium | Build Job Bank parser last (M4) when infrastructure is mature; store raw email bodies; documented fallback to direct scraping of `jobbank.gc.ca/jobsearch/` (low-risk for personal-use volumes per RESEARCH-REPORT.md §8 Risk 3). |

---

## Document references

- `projects/jd-matcher/docs/discovery/DISCOVERY-NOTES.md` — source of truth for design decisions
- `projects/jd-matcher/docs/discovery/RESEARCH-REPORT.md` — ingestion feasibility, source matrix
- `projects/jd-matcher/docs/discovery/MARKET-ANALYSIS.md` — commercial thesis, Beta gates
- `projects/jd-matcher/docs/discovery/UX-SPEC.md` — single web surface design

---

## Session Summary Output

```
Roadmap: jd-matcher
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Discovery (complete)
  Requirements locked, ingestion architecture validated, UX designed, market thesis written.
  Exit: ROADMAP.md user-approved

PoC (active phase next)
  Validate four critical components against hand-labeled samples on a working
  local web app. Personal-first; commercial hedges threaded into milestones.
  Local-only, single-user, SQLite, FastAPI, cloud LLM by default
  (gpt-4o-mini + text-embedding-3-small, ~$0.65/mo); local Ollama optional.
  Critical components:
    - Ingestion + JD hydration — ≥95% URL extraction & hydration (deterministic)
    - Content-aware dedup — ≥90% on 30 pairs; 0 false-merges on different-team
    - LLM extract+classify+fit — ≥80% primary tag, ≥90% fit accept/reject
    - CV recommender — ≥80% top-1 agreement on 20 postings (user approval)
  Milestones:
    M1 — Fresh LinkedIn+Indeed jobs from Gmail + applied/dismissed state from
         week 1 (URL-based dedup, no posting reappears) (~1 wk + 1 day)
    M2 — Content-aware dedup merges cross-source postings; repost detection
    M3 — Cards arrive pre-classified, pre-scored, pre-filtered (cloud LLM)
    M4 — CV recommendation per card; +Job Bank/Remotive/Jobicy/HN; analytics view
  Exit: All four components meet thresholds; user approves M4 deliverable;
        quality logs stored; PHASE-REVIEW.md user-approved.

MVP
  Run unattended daily for 4-8 weeks of real job-search use. Reliability
  hardening (launchd, OAuth refresh, per-source resilience), coverage expansion
  based on PoC gaps, French support, dismissal-learning, settings expansion.
  Exit: 28 days unattended; ≤5 min median triage; user approves durability;
        Beta-gate evaluation chooses Variant A or B.

Beta
  Decision gate. All three MARKET-ANALYSIS Beta gates pass → Variant B
  (multi-tenant rewrite, ingestion overhaul, OSS+managed-tier). Any gate
  fails → Variant A (durability hardening for ongoing personal use).
  Exit (A): 6 months stable use post-Beta-A; runbook documented.
  Exit (B): 3 articulated personas; ≥3 external pilot users; ToS-clean
           ingestion; ≥80% accuracy on extended 100-posting benchmark;
           ≥1 managed-tier conversion OR ≥500 GitHub stars.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
