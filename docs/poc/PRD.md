# Product Requirements Document — jd-matcher (PoC)

> **Status**: Draft
> **Phase**: PoC
> **Last Updated**: 2026-04-24
> **Depends on**: DISCOVERY-NOTES.md, MARKET-ANALYSIS.md, ROADMAP.md, RESEARCH-REPORT.md, UX-SPEC.md (all approved)

---

## 1. Overview

jd-matcher is a local-only desktop tool that consolidates job postings from LinkedIn, Indeed, Job Bank Canada, and several open-API sources (Himalayas, Remotive, Jobicy, HN "Who is Hiring") into a single browser-based daily-triage workflow. It deduplicates across sources with content-aware matching that respects same-title-different-team distinctions, applies an LLM-driven role-fit filter tuned to data-driven problem-solving roles, classifies each posting by technical focus (LLM/GenAI, Traditional ML, Causal Inference, etc.), and recommends one of 5 pre-existing CV variants per posting. The user-facing surface is a single FastAPI-served page on `localhost:PORT` with three tabs (Main / Applied / Dismissed) — keyboard-first, optimised for clearing 5–20 cards in under a minute (per UX-SPEC.md). See DISCOVERY-NOTES.md §1 for problem framing.

---

## 2. Target User

A single user — the project author. Not a persona document.

| Attribute | Value |
|-----------|-------|
| Role | Data Scientist & ML Engineer |
| Location | Vancouver, BC |
| Immigration status | Open Work Permit holder; PR-eligibility path requires a Canadian employer |
| Search shape | Active daily; current baseline ~20–45 min/day across 4 platforms; <5 applyable postings/day surfaced manually (DISCOVERY-NOTES.md §1) |
| Technical comfort | Builds the tool themselves; can run a local Python stack and configure a `.env` |
| LinkedIn risk tolerance | Zero account-ban tolerance — no authenticated automation against LinkedIn |
| CV portfolio | 5 pre-tuned variants on local filesystem (no rewriting in scope) |
| Hardware | Personal desktop — no employer-machine constraints |

The author is the only user PoC and MVP serve. Beta evaluates whether external personas exist (see §3).

---

## 3. Commercial Thesis

**Personal-first throughout PoC and MVP.** The user is actively job-hunting and urgency is the dominant constraint; commercial-first would delay usable output by months. Per MARKET-ANALYSIS.md, commercial viability is "Low-to-Medium, conditional on Beta gate validation" — the niche of "Vancouver DS/ML + OWP" is too small to anchor a commercial product, and any commercial path requires generalising the tool to senior technical job seekers globally with cross-source aggregation pain.

The PoC adopts five architectural hedges (DISCOVERY-NOTES.md §10.5) so the eventual commercial decision is not a rewrite. None alters the personal-first scope:

| # | Hedge | What it preserves |
|---|-------|------------------|
| 1 | Classify always, filter configurably | Full classification persisted on every posting; filtering is a view policy (`fit_threshold` config). Below-threshold rows remain queryable. |
| 2 | Time-savings instrumentation | `events` table records `card_viewed`, `card_dismissed`, `card_marked_applied`, session start/end with timestamps. Surfaces via `/analytics` view at M4. Logged in PoC; **evaluated at MVP** (Beta Gate 1 input). |
| 3 | Namespace-aware data model | Every table has a `user_id` column defaulted to `'default'`. Multi-tenant rewrite becomes additive, not ground-up. |
| 4 | Taxonomy portability | Classification prompt and tag taxonomy written in role-family-generic language. Ports to other technical roles without rewrite. |
| 5 | Open-source from day 1 | Public GitHub repo + MIT LICENSE + README from M1 task one (also satisfies portfolio default). |

**Deferred to pre-Beta**: hand-labeled benchmark extension from 30 → 100 postings (DISCOVERY-NOTES.md §10.5).

**Acknowledged commercial wall**: LinkedIn ToS exposure at commercial scale (HiQ Labs precedent — MARKET-ANALYSIS.md Risk 1). The guest-endpoint JD hydration approach used in PoC cannot scale commercially; any commercial pivot requires a different LinkedIn ingestion layer (email-only or paid aggregator). No PoC architectural choice solves this — it is a Beta-B problem.

**Beta gates (verbatim from ROADMAP.md and MARKET-ANALYSIS.md §"Beta-Transition Decision Framework")** — all three must pass for the commercial thesis to be worth exploring at end of MVP:

> **Gate 1 — Time savings**: ≤5 min/day median triage on ≥80% of days over a 3-week window. Source: analytics view (hedge 2 instrumentation).
>
> **Gate 2 — Coverage superiority**: ≥3 relevant postings/week from non-LinkedIn sources over the MVP window. Source: M4 + MVP coverage audit.
>
> **Gate 3 — Generalisable personas**: User can name ≥2 reachable communities outside DS who share the same pain. Source: user reflection + market-analyst review.

All three pass → Variant B candidate (commercial spike). Any fails → Variant A (stay personal).

---

## 4. Phase Objectives

PoC validates the four capabilities that determine whether the rest of the system can be trusted, on a working local web app:
1. Multi-source ingestion (Gmail email parsing for LinkedIn/Indeed/Job Bank + JD hydration; direct-API polling for Himalayas/Remotive/Jobicy/HN)
2. Content-aware deduplication (LLM-extracted fields + embedding similarity, two-stage)
3. LLM single-call extraction + classification + role-fit scoring
4. CV-to-posting recommender (cosine on embeddings)

Each milestone ends with a user-observable web-UI deliverable on real data.

**ROADMAP.md PoC exit criteria — verbatim**:

> 1. All four critical components meet thresholds in their validation milestones.
> 2. User has run the end-to-end flow on real data through M4 and approved the deliverable.
> 3. ≥30-pair dedup hand-label, ≥30 LLM-extraction hand-label, ≥20 CV-recommender hand-label, all stored in `quality-logs/`.
> 4. Time-savings instrumentation captures session events; analytics page shows at least one full triage session end-to-end.
> 5. PHASE-REVIEW.md produced and user-approved.

---

## 5. Scope IN

Four milestones, each with a user-observable deliverable. Mirrors ROADMAP.md §"PoC Milestone Decomposition" exactly.

### M1 — Raw pipe + URL dedup + applied/dismissed state
- Gmail OAuth loopback flow; Gmail API ingestion of LinkedIn + Indeed alert emails
- LinkedIn alert parser (URL-regex primary on plain-text part); Indeed alert parser
- JD hydration via LinkedIn / Indeed public guest endpoints (rate-limited 1 req / 30s)
- SQLite schema with `user_id` namespace column on every table (hedge 3) + `events` table (hedge 2)
- `seen_urls` table + URL-based dedup check on ingest
- `applied` and `dismissed` state tables; state-aware Main view query
- FastAPI app skeleton with three tabs (Main / Applied / Dismissed) per UX-SPEC.md §1–§2
- `[Mark Applied]` and `[Dismiss]` buttons with persistent state (incl. across server restart)
- `/pipeline/run` endpoint
- Public GitHub repo with README "Built with Claude Code" badge + MIT LICENSE (hedge 5)

### M2 — Content-aware dedup + repost detection
- LLM extraction call producing `canonical_company / canonical_seniority / canonical_location / team_or_department / top_skills / role_summary` (used here for normalisation only — full classification deferred to M3). **LLM provider: cloud-default — OpenAI `gpt-4o-mini` for extraction; `text-embedding-3-small` for embeddings. Local-swap (Ollama + sentence-transformers `all-MiniLM-L6-v2`) is preserved as architecture (clean `LLMExtractor` / `EmbeddingProvider` interface, see TDD §C28) but not the default — see ROADMAP §M3 optional benchmark sub-task and BACKLOG (M2 cost-watchdog).**
- Cloud embedding pipeline (`text-embedding-3-small`; config-swappable to local `all-MiniLM-L6-v2` per the same provider abstraction)
- Two-stage dedup: block by `(canonical_company, canonical_seniority, canonical_location)`; fuse cosine + structured similarity at 50/50
- Canonical record merge logic preserving `first_seen` + `sources[]`. Merge semantics (user-confirmed at M2 planning): canonical_title/company/location use the LLM-canonicalized values as the single source of truth; first_seen = earliest of merged postings; sources[] accumulates all source variants (e.g. `["linkedin", "indeed"]`); apply URL renders both sources as separate links per card; full_jd picks the longer variant and records provenance; applied/dismissed state inherits across the canonical.
- Cross-state dedup generalised to canonical-id (a new posting matching an applied or dismissed canonical is suppressed from Main). **Exception**: a new posting matching a canonical that is currently in `Inactive` OR `Expired` state is NOT suppressed — both states are treated as non-existent for dedup purposes (URL-based and LLM content-based dedup paths). The new posting surfaces on Main with a fresh posting_id; the old Inactive/Expired entry remains visible (Applied tab Inactive sub-section for Inactive; Dismissed tab Expired sub-section for Expired) as forensic history. (See BACKLOG.md → "Inactive AND Expired state lifecycle" — implemented at MVP-M1.) **The dedup-bypass predicate is wired into the M2 dedup engine (TDD §C21 / §C22) as a no-op at M2** — the `applied.status` enum in M1 has only `'Applied'`, so the `WHERE status NOT IN ('Inactive', 'Expired')` guard matches everything; MVP-M1's status-enum extension flips the predicate to load-bearing without any C21/C22 code change.
- Repost detection (same JD, new `jobId`, 30+ days later — threshold config-driven, default 30 per ROADMAP §M2)
- ~~Himalayas API source added~~ — **deferred to M4** (see BACKLOG.md → "PoC-M4 — Himalayas API source (deferred from M2)"). Bundles with M4's planned Job Bank/Remotive/Jobicy/HN multi-source expansion. M2 cross-source merge ACs validated against LinkedIn↔Indeed pairs only.

### M3 — Smart layer
- Single LLM extraction prompt (cloud-default OpenAI `gpt-4o-mini`, ~$0.60/mo at 20 postings/day; Ollama `qwen2.5:7b` config-swappable) producing all of: canonical fields + salary + tags + `primary_focus` + `fit_score` + `fit_reasoning` + `requires_pr_or_citizenship`
- Hard-filter Layer 1 keyword pre-LLM list for PR/citizenship
- Soft-rank composite scoring (salary + industry + recency, configurable weights)
- Main view sort + filter as a view policy (hedge 1) — below-threshold postings remain queryable
- Taxonomy revision pass after ~100 classified postings (rename/merge/split)
- Generic role-family-language prompt (hedge 4)
- Optional opt-in: local-vs-cloud LLM benchmark sub-task (Ollama vs `gpt-4o-mini`) — results (if the opt-in is run) are an input to the Beta Path B evaluation: whether local-Ollama quality is equivalent to `gpt-4o-mini` determines whether a free local + paid cloud-tier model is commercially viable.

### M4 — CV recommender + extended sources + analytics
- CV text extraction (PyMuPDF or pdfplumber) at startup; CV embedding pipeline (same `text-embedding-3-small`); cosine rank against `role_summary + top_skills` embedding
- Top-1 CV recommendation per card + override dropdown (all 5 ranked); override persists per posting
- Settings page accepting 5 CV filesystem paths (UX-SPEC.md §9 PoC scope)
- Job Bank Canada email parser
- Remotive API client (`category=ai-ml`)
- Jobicy API client (`geo=canada`)
- HN HNRSS regex parser
- Analytics view at `/analytics` (hedge 2 surface) — median time-per-card, sessions/day, time-to-clear-inbox, dismiss/apply ratio
- Coverage gap audit task — record sources/queries that contributed unique postings (Beta Gate 2 input data)

### Cross-cutting (threaded across all milestones)
- Configurable knobs in config file (DISCOVERY-NOTES.md §10) — no hardcoded thresholds
- Quality logs for every milestone in `projects/jd-matcher/docs/poc/quality-logs/`
- Per-source isolation — one source failure does not cascade

---

## 6. Scope OUT

Permanently out (DISCOVERY-NOTES.md §14):
- Auto-apply on user's behalf
- LLM CV rewriting / generated CVs (only selection from the 5 pre-existing variants)
- Mobile app, push notifications, email/SMS alerts
- Interview prep, salary negotiation, offer comparison

Deferred to MVP (DISCOVERY-NOTES.md §14, ROADMAP.md §"Out of scope (PoC)", UX-SPEC.md §"What NOT to Build"):
- Multi-tenant infrastructure beyond the namespace-aware schema hedge
- Authentication / user accounts
- Cloud hosting
- French-language postings (English-only in PoC)
- Cross-location merge pass (multi-location reposting accepted as separate cards)
- "Possible duplicate" UI hint (ambiguous-zone surfacing)
- Soft-rank weight UI sliders, fit-score threshold slider, tag taxonomy editor
- Dismissal-learning loop (PoC: dismiss = blacklist, no feedback signal)
- Cron / launchd full automation (PoC: basic schedule + manual `/pipeline/run` only)
- Greenhouse / Lever ATS API sources (curated employer slug list — deferred unless coverage gap surfaces in M4 audit)
- Coverage expansion based on PoC audit (additional LinkedIn keywords, French embeddings, Greenhouse) → MVP-M2
- Inactive AND Expired state lifecycle (auto-Inactivate `Applied`/`Screen`/`Interview` after ~90 days of silence on `status_updated_at`; auto-Expired on hydrator HTTP 404; dedup bypass for both states; Applied tab Inactive sub-section; Dismissed tab Expired sub-section; manual Inactive→any-status transition by user) — supersedes the original auto-remove design — MVP-M1
- Inactive accumulation reminder notification (separate from Inactive lifecycle; surfaces a UI prompt when Inactive count crosses a threshold, since Inactive entries never auto-remove) — MVP (separate item from Inactive lifecycle)

Deferred indefinitely or to Beta (DISCOVERY-NOTES.md §3, §14, MARKET-ANALYSIS.md):
- Google for Jobs (no free RSS path; SerpAPI free tier marginal, paid breaks budget)
- Monster Canada (coverage too thin for Canadian DS/ML)
- Wellfound / AngelList (no official API; weak Canadian coverage)
- aijobs.net (RSS behind $17/mo paywall)
- Direct company career pages (per-site scraping maintenance)
- Commercial distribution / managed-tier signups (Beta Variant B only)
- Hand-labeled benchmark extension from 30 → 100 postings (DISCOVERY-NOTES.md §10.5 — pre-Beta if commercial pursued)

---

## 7. Success Criteria

Anchored to ROADMAP.md PoC exit criteria + per-milestone acceptance criteria.

| # | Criterion | Target | Measurement | Validated in |
|---|-----------|--------|-------------|--------------|
| SC-1 | LinkedIn URL extraction from alert emails | ≥95% | ≥50 historical alert emails, deterministic | M1 |
| SC-2 | Indeed URL extraction from alert emails | ≥95% | ≥30 historical alert emails, deterministic | M1 |
| SC-3 | JD hydration (LinkedIn + Indeed guest endpoints) | ≥95% | ≥30 sample URLs, deterministic | M1 |
| SC-4 | URL-based dedup | 100% | Re-run pipeline against same Gmail inbox; zero re-additions | M1 |
| SC-5 | State persistence (applied/dismissed across server restart) | 100% | End-to-end test, deterministic | M1 |
| SC-6 | Content-aware dedup overall | ≥90% on 30 hand-labeled pairs | 10 dup / 10 non-dup / 10 ambiguous | M2 |
| SC-7 | Content-aware dedup — different-team false-merge rate | **0** | 10 different-team cases — regression-blocking | M2 |
| SC-8 | Cross-source merge | Verified | ≥3 real LinkedIn + Indeed pairs collapse to one card | M2 |
| SC-9 | LLM `primary_focus` agreement | ≥80% | ≥30 hand-labeled postings vs. user labels | M3 |
| SC-10 | LLM multi-tag Jaccard | ≥70% | Same set as SC-9 | M3 |
| SC-11 | LLM `fit_score` accept/reject agreement at threshold 50 | ≥90% | Same set as SC-9 | M3 |
| SC-12 | Salary extraction (where stated) | ≥90% within ±10% | Hand-labeled subset | M3 |
| SC-13 | Hard-filter PR/citizenship pre-LLM rejection | 0 false-negatives on 10 test cases | Synthetic + real | M3 |
| SC-14 | Cloud-LLM cost over milestone window | ≤$1/mo | `quality-logs/llm-cost.md` | M3 |
| SC-15 | Below-threshold postings remain queryable (hedge 1 proven) | Visible count in events/admin view | M3 acceptance check | M3 |
| SC-16 | CV recommender top-1 agreement | ≥80% on 20 hand-labeled postings (probabilistic — user approval gate) | Hand-label review | M4 |
| SC-17 | Job Bank Canada email parsing | ≥90% URL extraction on ≥10 real emails | Risk 3 from RESEARCH-REPORT.md §8 — fragile | M4 |
| SC-18 | Extended-source ingestion (Remotive, Jobicy, HN, Job Bank) | ≥1 real posting each, ≥95% structural success | Deterministic | M4 |
| SC-19 | Time-savings instrumentation captures one full triage session end-to-end (hedge 2 deliverable) | `/analytics` shows session start → triage → close | **Logged in PoC; commercial evaluation at MVP only — Beta Gate 1 input** | M4 |
| SC-20 | Coverage audit report | Per-source unique-contribution count over M4 window | Beta Gate 2 input | M4 |
| SC-21 | All four critical components meet quality bars; user runs end-to-end on real data; PHASE-REVIEW.md user-approved | Phase exit | ROADMAP.md exit criteria 1–5 | End of M4 |

---

## 8. Constraints

| Constraint | Detail | Source |
|-----------|--------|--------|
| Runtime | Local-only on user's personal desktop. No hosting, no multi-tenant, no PIPEDA-scope processing. | DISCOVERY-NOTES.md §9 |
| LLM default | Cloud — OpenAI `gpt-4o-mini` (extraction) + `text-embedding-3-small` (embeddings). Combined ~$0.65/mo at 20 postings/day. Local Ollama `qwen2.5:7b` + `all-MiniLM-L6-v2` config-swappable. **Cloud-default chosen explicitly to avoid multi-GB local model downloads multiplying across the portfolio.** | DISCOVERY-NOTES.md §10 / ROADMAP.md §PoC scope |
| Timeline | ASAP — user is actively job-hunting; "1 day less = 1 day benefit." M1 must produce a usable daily output within ~1 week + 1 day. | DISCOVERY-NOTES.md §11 |
| LinkedIn account risk | **Zero tolerance.** No authenticated automation. Email-alert ingestion + public guest-endpoint hydration only (rate-limited 1 req / 30s). | DISCOVERY-NOTES.md §3 |
| LinkedIn ToS posture | Guest-endpoint hydration is technically ToS-gray; explicitly accepted at single-user personal volume. **Documented in TDD §4.** | DISCOVERY-NOTES.md §3 |
| Immigration filter (OWP) | First-class concern. Hard-filter rules reject postings requiring existing PR, Canadian citizenship, security clearance, US citizenship, or stating "no sponsorship". Config-driven keyword list, grown organically. | DISCOVERY-NOTES.md §2, §6, §12 |
| Manual prerequisites | User must set up: dedicated Gmail account + 7 LinkedIn saved searches + 2–3 Indeed alerts + Job Bank Canada alerts + 5 CV file paths + OpenAI API key — before pipeline can run. Documented in DATA-SOURCES.md §"Manual setup checklist". | DISCOVERY-NOTES.md §3, §4; RESEARCH-REPORT.md §9 |
| Storage | SQLite for PoC. PostgreSQL deferred to MVP if needed. | DISCOVERY-NOTES.md §9 |

---

## 9. Risks & Mitigations

Top 5 from ROADMAP.md §"Risks and Mitigations" — synthesised here for product-level scope decisions, not re-authored.

| Risk | Source | Likelihood | Impact on Scope | Mitigation |
|------|--------|-----------|----------------|-----------|
| R1 — LinkedIn alert email template change silently breaks parser | Tech (RESEARCH-REPORT.md §3, §8) | Medium-High | URL-only fallback ships in M1; "URL-only fraction" health metric guards against silent regression | URL-regex-first parser; raw email body stored for replay; alert if URL-only fraction >20% |
| R2 — Gmail OAuth refresh token revoked | Tech (RESEARCH-REPORT.md §8) | Medium | Pipeline halts for Gmail sources; API sources continue (per-source isolation) | Startup health check; clear "Re-run auth flow" error; persistent banner per UX-SPEC.md §8 |
| R3 — LinkedIn / Indeed rate-limit or IP-block at hydration | Tech (DISCOVERY-NOTES.md §3, ROADMAP.md R3) | Medium | Degrade gracefully — store URL even if hydration fails; fall back to email teaser | 1 req / 30s rate limit; ~40 hydrations/day total |
| R4 — User's LinkedIn saved searches too narrow → coverage gap | Tech / UX (ROADMAP.md R4) | Medium | M4 coverage audit explicitly tracks unique-source contributions; coverage expansion goes to MVP-M2 | M4 audit task; DISCOVERY-NOTES.md §4 lists candidate keyword expansions |
| R5 — Job Bank Canada email parser fails (gov't IT cycle) | Tech (RESEARCH-REPORT.md §8 Risk 3) | Medium | Built last (M4) so infrastructure is mature; fallback to direct scrape of public search page is feasible at personal volume | Raw email bodies stored; documented fallback to `jobbank.gc.ca/jobsearch/` |

---

## 10. Open Questions

These remain open at PoC kickoff and will be resolved at the corresponding milestone-planning step. Do not pre-decide:

1. **Final exact LinkedIn keyword list** — DISCOVERY-NOTES.md §4 lists 7 seed keywords + 4 candidates ("AI Engineer", "Applied AI Research", "ML Research Scientist", "Quant Research"). Final list confirmed at M1 milestone-plan.
2. **Indeed and Job Bank query specifics** — DISCOVERY-NOTES.md §4 says architect formalises in ingest TDD. Confirmed at M1 / M4 milestone-plan.
3. **Tag taxonomy revision details** — seed 10 tags from DISCOVERY-NOTES.md §7; final rename/merge/split decided at M3 against ~100 real classified postings.
4. **Auto-merge similarity threshold** — default 0.90 from DISCOVERY-NOTES.md §10; calibrated against hand-labeled 30 pairs at M2.
5. **`fit_threshold`** — default 50 from DISCOVERY-NOTES.md §10; calibrated against hand-labeled set at M3.
6. **Local Ollama benchmark opt-in at M3** — runs only if user explicitly opts in; not a default deliverable.
7. **`[Run sync now]` placement, two-column layout, `Business Analytics / BI` dimming, Dismissed-tab placement, CV filename labelling, Applied-tab default sort** — UX-SPEC.md §"Open UX Questions". Resolved by ux-designer at PoC milestone-plan or deferred to MVP-M3.
8. **Q4 from RESEARCH-REPORT.md §9** — Greenhouse/Lever curated employer list — declined for PoC; revisit at MVP-M2 based on M4 coverage audit.
