# jd-matcher — Discovery Notes

**Date**: 2026-04-24
**Status**: Locked after Step 1 conversation + research-analyst pre-discovery feasibility study.

---

## 1. Problem & user

**Who**: The project author — a Vancouver-based Data Scientist / ML Engineer, actively job-hunting.

**Pain points (in order)**:
1. **Too many sources, too many duplicates** — LinkedIn, Indeed, Google Jobs, Monster each surface overlapping postings; manual triage is time-consuming.
2. **Confusing job titles** — a "Data Scientist" role at one company is a dashboard builder at another; current workflow requires reading every JD to confirm fit.
3. **CV mismatch** — suitable postings span different technical focuses (Traditional ML / NLP / LLM / causal inference / etc.); user adapts their CV per posting.

**Current state**: With manual screening across all sources, user identifies fewer than ~5 applyable postings per day. Target with the system: **"clear all new suitable postings in under a minute per day"**.

**Ambition**: Personal-use tool. Commercial optionality to be re-evaluated at Beta transition (market-analyst).

---

## 2. User profile & criteria (filters)

### Role fit (judgment, LLM-driven)
- **Must be**: data-driven problem-solving — use data + ML/statistics to answer business questions or build data products. "Thinking of solutions that can solve business problems" is the user's own framing.
- **Must not be**: pure dashboard development, pure software engineering, pure analytics reporting, pure ML infra/MLOps.

### Hard filters (deterministic)
- **Location**: Vancouver-based OR remote with Canadian employer.
- **Seniority band**: Intermediate / Senior / Staff / Principal / Lead / Manager. Junior/intern REJECT.
- **Immigration**: User holds an **Open Work Permit**. PR eligibility path requires employment by a **Canadian employer**.
  - HARD REJECT: postings that require existing PR, Canadian citizenship, security clearance, US citizenship, or state "no sponsorship".
- **Language**: English. French postings deferred to MVP.

### Soft ranking signals (affect sort, not filter)
- Higher salary → rank higher
- Industry ∈ {Finance, Insurance} → rank higher
- Fresher posting → rank higher
- Company size: **deferred to MVP** (requires external data sources not budgeted for PoC).

### "Already applied" state
- User has a dedicated job-search Gmail account (already exists).
- Posts that match something in the user's applied or dismissed state MUST NOT appear in the main blog.
- Dismissed = permanent blacklist.
- Applied entries auto-remove from the applied view after 3 months of unchanged status.

---

## 3. Ingestion architecture (validated by research-analyst 2026-04-24)

**Two parallel ingest paths** flowing into the same dedup/filter/classify pipeline:

### Path A — Gmail email-alerts (closed platforms)

Used for sources that gate programmatic access but provide structured email alerts.

| Source | Why email | Setup |
|---|---|---|
| **LinkedIn** | No free API; scraping would risk account ban (user-vetoed). Alert emails push the list to us without any search request hitting LinkedIn. | User sets up ~7 overlapping daily saved searches (see §4). |
| **Indeed.ca** | Publisher API deprecated 2023. Email alerts remain supported. | User sets up 2–3 daily alerts. |
| **Job Bank Canada** | No RSS or search API; monthly bulk data is too stale. Government board — every employer is validated as Canadian-eligible-to-hire, directly addressing the work-permit filter. | User sets up email alerts on jobbank.gc.ca. |

**Mechanism**: Gmail API (read-only, loopback OAuth for desktop app) polls the dedicated job-search account hourly. Emails filtered by sender address per source, parsed by per-source parsers. `messages.list` + `messages.get` well under free quota for personal use.

### Path B — Direct API polling (open platforms)

Used for sources that offer free structured APIs — strictly better than email parsing where available because JDs are complete from the start.

| Source | Endpoint | Notes |
|---|---|---|
| **Himalayas** | `himalayas.app/jobs/api/search` | Free, no auth. ~93 live Canadian DS results (research-confirmed). 17 structured fields. |
| **Remotive** | `remotive.com/api/remote-jobs` | Free, no auth. Filter by `category=ai-ml` or `category=data`, then post-filter by location. |
| **Jobicy** | `jobicy.com/api/v2/remote-jobs` | Free, no auth. Thin Canadian DS coverage (2 results in test) but zero marginal cost. |
| **HN "Who Is Hiring"** | `hnrss.org/whoishiring/jobs` | Free RSS. Low volume, high signal. Free-text parsing with regex. |

### JD hydration for LinkedIn / Indeed (critical design)

LinkedIn and Indeed alert emails contain only a **short teaser**, not the full JD. Full JDs are required for:
- User decision-making
- CV-recommender input
- Content-based dedup
- Technical focus classification

**Mechanism**: for each newly extracted URL (once per URL, ever), fetch the **public logged-out guest endpoint** (`linkedin.com/jobs-guest/jobs/api/jobPosting/{jobId}` for LinkedIn; equivalent public page for Indeed). Rate-limited to 1 request per 30 seconds.

**Parsing**: reuse JD-extraction code from OSS libraries (`py-linkedin-jobs-scraper`, JobSpy). **Do not call their list/search methods** — the search-step is the risky automation fingerprint they warn about. We only use them for the hydration step after emails have already delivered the URL.

**Risk profile** (explicitly accepted by user):
- **Zero LinkedIn-account risk** — no authentication, no login, no cookie.
- **Low IP-block risk** — volume is ~40 unique hydrations per day, indistinguishable from a human clicking slowly.
- **Technically ToS-gray** — LinkedIn's ToS broadly prohibits automation. At single-user personal volume, enforcement risk is very low. This trade-off was presented explicitly and accepted.

### Sources explicitly excluded from PoC

| Source | Reason |
|---|---|
| **Monster Canada** | Coverage too thin for Canadian DS/ML to justify engineering effort. |
| **Wellfound (AngelList)** | No official API path; weak Canadian coverage. |
| **Google for Jobs** | No free RSS/email path. SerpAPI free tier (~250/mo) marginal; paid tier ($25/mo) breaks budget. Revisit at MVP if coverage gap emerges. |
| **aijobs.net** | RSS/alerts behind $17/mo paywall. |
| **Greenhouse / Lever ATS APIs** | Would require curating 20–30 Canadian-employer slugs. User declined the curation overhead for PoC — revisit at MVP only if coverage gap emerges. |
| **Direct company career pages** | Per-site scraping maintenance cost. Revisit at MVP for missed high-value employers. |

---

## 4. LinkedIn search coverage strategy

**Principle**: missing a role is worse than duplicate emails. The dedup layer collapses overlap for free, so coverage should be **generous**.

User to set up **7 daily saved searches** on LinkedIn (Vancouver + Remote Canada):

| # | Search keyword |
|---|---|
| 1 | Data Scientist |
| 2 | Senior Data Scientist |
| 3 | Machine Learning Engineer |
| 4 | Applied Scientist |
| 5 | Data Science |
| 6 | Research Scientist |
| 7 | Staff Data Scientist |

Similar overlapping coverage for Indeed.ca and Job Bank Canada (architect to formalize exact queries per platform in the ingest TDD).

**Additional coverage gaps** (to add iteratively if PoC shows missed roles): `AI Engineer`, `Applied AI Research`, `ML Research Scientist`, `Quant Research` (for finance).

---

## 5. Dedup design

### Requirement (explicit)

Dedup MUST handle the "same company + same title + different team" case — e.g. two "Senior Data Scientist" postings at Shopify for distinct teams must NOT be merged.

### Design: content-aware, two-stage, hybrid (LLM-extracted fields + embeddings)

Every new posting runs through **one LLM extraction call** (see §7) that produces structured fields used by every downstream step, including dedup.

**Stage 0 — Normalization**
LLM-extracted fields serve as canonical: `canonical_company`, `canonical_seniority`, `canonical_location`, `team_or_department`, `top_skills`, `role_summary`. More robust than regex-based normalization for abbreviations, subsidiaries, and varied phrasings.

**Stage 1 — Blocking**
Composite key: `(canonical_company, canonical_seniority, canonical_location)`.
Team is **not** in the block key (so different-team-same-role postings land in the same block for explicit comparison).

**Stage 2 — Similarity (two parallel signals, fused)**
- **Signal A**: cosine similarity on full-JD embedding (`sentence-transformers/all-MiniLM-L6-v2`, local, ~80MB, CPU-friendly, zero cost).
- **Signal B**: structured-field match — `team_or_department` equivalence, `top_skills` Jaccard overlap, `role_summary` similarity.
- **Fusion**: weighted combination (default 50/50, tunable).

**Decision thresholds (starting values, calibrated during PoC)**:

| Fused similarity | Action |
|---|---|
| ≥ 0.90 | Auto-merge |
| 0.75 – 0.90 | Keep separate in PoC; "possible duplicate" hint deferred to MVP |
| < 0.75 | Keep separate (different roles / different teams) |

**Bias**: strict auto-merge threshold. Over-merge (losing a real job) is worse than under-merge (minor UI noise).

**Stage 3 — Canonical record**
- Longest/richest JD wins as canonical description
- `sources[]`: every origin + apply URL + first-seen-per-source timestamp
- `first_seen`, `last_seen` across all sources
- Permanently stored; embeddings cached to avoid recomputation

**Repost detection**: LinkedIn reposting an identical JD under a new jobId after 30-60 days → Stage 2 signal A + B both flag as duplicate → merged into existing canonical with preserved `first_seen`.

### Acknowledged corner cases

- **Multi-location reposting** — same req posted separately for Vancouver + Toronto + Montreal. PoC: accepted as 3 cards (different blocks). MVP: add cross-location merge pass if noisy.
- **Bilingual postings (French/English)** — PoC English-only. MVP: add French with French-capable embedding model.
- **Title band edge cases** — odd titles ("Lead of Applied Research", "Quant Strategist") may land in surprising bands. Architect builds + audits normalizer against sample.

### Quality bar for PoC (Gate 4)

Hand-label ≥30 posting pairs:
- 10 clear duplicates (same job, multiple sources)
- 10 clear non-duplicates (different jobs, same company/title — the "different team" case)
- 10 ambiguous

**Pass**: ≥90% accuracy on clear cases; **zero** false-merges on the "different team" cases (signal protection is paramount).

---

## 6. Filter design

### Layer 1 — Hard deterministic rules (zero-cost)

Applied first. Kills ~60–70% of postings before any LLM call.

| Rule | Logic |
|---|---|
| Location | ACCEPT if `canonical_location ∈ {Vancouver-BC, Remote-Canada, Hybrid-Vancouver}`; else REJECT |
| Seniority | ACCEPT intermediate/senior/staff/principal/lead/manager; REJECT intern/junior; ACCEPT unknown (let LLM decide) |
| PR/citizenship | REJECT if `requires_pr_or_citizenship: true` (LLM-extracted). Seed keyword list for pre-LLM fast reject: "Canadian citizen", "permanent resident", "PR required", "security clearance", "US citizenship", "no sponsorship" |
| Language | English only for PoC |

### Layer 2 — LLM role-fit score (0–100)

Same single LLM call that does extraction also outputs `fit_score` and `fit_reasoning`.

**Architectural principle: classify always, filter configurably.** Every posting is classified and persisted — nothing is discarded based on filter policy. Filtering is a **view policy**, not a storage decision. Default main-blog view shows `fit_score ≥ 50`; below-threshold postings remain in the database and are reachable via a future "all postings" view or by adjusting the threshold in config. This decouples the classification primitive from the filter policy and is a foundational commercial-optionality hedge (see §10.5).

**Threshold**: `fit_score ≥ fit_threshold` (default 50, configurable) → surfaced in main blog. Below → hidden from main view, still stored with full classification.

**Starting model**: **cloud-default — `gpt-4o-mini`** for extraction. User explicitly requested cloud-first to avoid downloading multi-GB models that would multiply across portfolio projects. Local Ollama (`qwen2.5:7b`) remains an optional fallback configurable via `llm.extraction_model`. Estimated PoC cost at 20 postings/day: ~$0.60/month. Alternative provider options (DeepSeek, Gemini Flash, Claude Haiku 4.5) are config-swappable.

### Layer 3 — Soft ranking (not filtering, affects display order)

Composite sort score from: `salary_max_cad` (higher = higher), `industry ∈ {Finance, Insurance}` (bonus), recency decay. Weights configurable.

### Dismissal & feedback (PoC vs. MVP split)

- **PoC**: dismiss = hide from UI + add to permanent blacklist. No learning.
- **MVP**: dismissal reason categories + weekly review → tune threshold and keyword list.
- **Beta**: user applies → reinforce similar postings; CV-selection mismatches → model feedback.

---

## 7. Classification design (tags)

Every posting tagged with technical-focus labels using the same single LLM call (extraction + fit + classification in one prompt).

### Seed taxonomy (iterated during PoC, not pre-locked)

1. `Traditional ML` — classical ML on tabular data
2. `NLP` — pre-LLM linguistic/embedding work
3. `LLM / GenAI` — LLM apps, prompt engineering, RAG, agents
4. `Computer Vision`
5. `Recommender Systems`
6. `Time Series / Forecasting`
7. `Causal Inference / Experimentation` — A/B testing, product experimentation (high-signal for DS roles)
8. `MLOps / ML Infra` — flag significant infra component
9. `Applied Research` — research-flavored IC
10. `Business Analytics / BI` — usually user would avoid (auto-dim in UI)

**Multi-label + primary**: each posting gets 1–3 tags + one `primary_focus`. Example: `[Experimentation, Traditional ML]` with primary `Experimentation`.

**Taxonomy revision**: explicit PoC Milestone 3 task — after classifying ~100 real postings, merge/split/rename tags based on observed distribution. Not pre-decided.

### Quality bar (PoC Gate 4)

- `primary_focus` ≥ 80% agreement with user labels on hand-labeled sample
- Multi-tag ≥ 70% Jaccard overlap with user labels
- `fit_score` ≥ 90% agreement on binary accept/reject at threshold 50
- `salary_min/max_cad` extraction ≥ 90% exact-match or within ±10% where stated

---

## 8. UX & output

### Output surface (from user conversation)

- **Single web page**, opened in browser on desktop. Local-only, served at `localhost:<port>`. Pull-based (no push notifications).
- **Three views**:
  1. **Main blog** — new suitable + historically-unacted suitable postings
  2. **Applied blog** — user-marked applied postings with editable status; auto-remove after 3 months unchanged
  3. **Dismissed** — hidden from main and never resurfaced

### Per-posting card fields (all required)

- Title (with LLM-canonical and raw)
- Company
- Location
- Seniority
- Salary range (CAD)
- Industry
- Main technical focus (primary tag + secondary tags)
- Full job description
- Apply URL(s) — one per source
- Recommended CV variant (1 of 5 user-provided)
- Dismiss + "Mark applied" buttons

### CV handling — pure selection, no rewriting

User has **5 pre-existing CV variants**, each tuned to a different focus. System picks the best match per posting.

**Recommender approach** (to be formalized in PoC TDD):
- Represent each CV as an embedding (once, at ingest)
- Represent each job's `role_summary` + `top_skills` as an embedding
- Rank the 5 CVs by cosine similarity to the job; return top-1 as recommendation + scores for all 5

**Out of scope**: LLM rewriting of CVs. User applies manually via the posting's URL.

### State transitions

```
(new + suitable) → Main blog
                    ├─ [Dismiss] → Dismissed (never resurfaces)
                    └─ [Mark Applied] → Applied blog (editable status)
                                          └─ 3 months no-status-change → auto-remove
```

Dedup cross-checks every state: a new posting that matches a canonical in Applied or Dismissed is hidden from Main.

### Detailed UX to be produced by ux-designer (Step 3)

ux-designer will produce UX-SPEC.md + Claude Design Brief for this single web surface.

---

## 9. Runtime & deployment

- **Local-only** on user's desktop. No hosting, no multi-tenant, no PIPEDA scope.
- One-time Gmail OAuth (loopback flow, unverified-app Testing status — single user).
- Pipeline runs on a local schedule (cron / launchd) — hourly Gmail poll, daily full-run for API sources.
- Web UI served locally via FastAPI (aligned with portfolio standards).
- Persistent store: SQLite (PoC). Upgrade to PostgreSQL at MVP if needed.
- Secrets (Gmail OAuth tokens) in local `.env`, never committed.

---

## 10. Flexibility & configuration principles

Per explicit user direction, the solution is built with **configurable knobs**, not hardcoded values. Architect formalizes the config schema in the PoC TDD.

| Knob | Default | Tuned during |
|---|---|---|
| `dedup.auto_merge_threshold` | 0.90 | PoC Milestone 2 (dedup validation) |
| `dedup.fusion_weight_embedding` / `dedup.fusion_weight_structured` | 0.5 / 0.5 | PoC Milestone 2 |
| `dedup.block_key` | `(company, seniority, location)` | PoC Milestone 2 |
| `filter.fit_threshold` | 50 | PoC Milestone 3 (view policy — below-threshold postings still stored) |
| `llm.extraction_model` | OpenAI `gpt-4o-mini` (cloud-default) | Optional fallback to Ollama `qwen2.5:7b` if user later prefers local |
| `llm.embedding_model` | OpenAI `text-embedding-3-small` (cloud-default, ~$0.04/mo) | Optional fallback to local `all-MiniLM-L6-v2` |
| `classification.taxonomy` | 10-tag seed (role-family-generic) | Refined in Milestone 3 after 100 real postings |
| `filter.pr_keyword_list` | seed list | Grown from real dismissals |
| `ranking.weights` | salary/industry/recency equal | User preference (config file) |
| `user.current_user_id` | `"default"` | Namespace hedge — single value in PoC |

---

## 10.5 Commercial optionality hedges (adopted 2026-04-24)

Per user direction, the PoC will adopt five architectural hedges that preserve commercial optionality without meaningful cost to the personal-use timeline. All combined add ~4-6 hours of engineering work in PoC. User explicitly declined the sixth (extending the hand-labeled benchmark from 30 to 100) as PoC scope — that work is deferred to pre-Beta.

| # | Hedge | What it means in code | PoC cost |
|---|---|---|---|
| 1 | **Classify always, filter configurably** | Every posting stored with full classification; filter is a view policy (default `fit_threshold = 50`, config-adjustable). Below-threshold postings remain queryable. | ~1 hr — don't drop rejected records; threshold → config |
| 2 | **Time-savings instrumentation** | Log session events (card viewed / expanded / dismissed / applied, session start+end, time-per-card, time-to-clear-inbox) into a dedicated events table. Basic analytics view for own review. Enables the Beta Gate 1 commercial case. | ~2-4 hrs — events table, UI handlers, simple analytics page |
| 3 | **Namespace-aware data model** | Every table has a `user_id` column (default `'default'`). Queries filter by current user. Makes multi-tenant rewrite additive, not a ground-up redo. | ~1 hr — schema + query adjustments |
| 4 | **Taxonomy portability** | Classification prompt + tag taxonomy written in role-family-generic language, not DS-specific hardcoding. Same quality for personal use; ports to other technical roles without rewrite. | ~0 hrs — prompt phrasing only |
| 5 | **Open-source from day 1** | Public GitHub repo with README + LICENSE (MIT) from the first task, per portfolio default. Builds commercial-grade distribution/trust if a pivot happens. | ~0 hrs — already the portfolio default |

**Deferred to pre-Beta** (user explicitly moved out of PoC scope):
- Hand-labeled benchmark extended from 30 → 100. Extra labeling time (~3-4 hrs of user work) performed before Beta kickoff if commercial thesis is being explored.

**Not a hedge, but acknowledged commercial wall**: LinkedIn ToS exposure at commercial scale (HiQ Labs precedent). The guest-endpoint JD hydration approach chosen for PoC cannot scale commercially. Any commercial pivot requires a different ingestion layer for LinkedIn (email-only or paid aggregator). No architectural choice in PoC solves this.

---

## 11. Urgency & delivery shape

**User urgency**: ASAP — actively job-hunting, "1 day less = 1 day benefit."

**Proposed PoC milestone staging** (architect will formalize in ROADMAP.md):

| Milestone | Output (user-observable) | Rough effort |
|---|---|---|
| M1 — Raw pipe + state | Gmail ingest (LinkedIn + Indeed) + JD hydration + basic web UI with three tabs (Main / Applied / Dismissed). **URL-based dedup + applied/dismissed state buttons** included from day one so the UI is daily-usable without reappearing postings. No content-aware dedup, no classifier, no CV. First useful day. | ~1 week + ~1 day |
| M2 — Content-aware dedup | Cross-source content-aware dedup (Stage 0–3 — hybrid LLM-extracted-fields + JD embeddings, validated against hand-labeled sample). Repost detection. URL dedup from M1 generalizes to content dedup. | ~1 week |
| M3 — Smart layer | Cloud LLM extraction (fit + tags + salary + dedup fields). Hard filter + soft ranking. Classification UI. Taxonomy review task. | ~1 week |
| M4 — CV recommender + extended sources | CV variant ranking. Himalayas + Remotive + Jobicy + HN + Job Bank Canada. Time-savings analytics view (reads events table populated since M1). | ~1 week |

Architect to finalize milestones + acceptance criteria in ROADMAP.md.

---

## 12. Explicit decisions deferred to PoC tasks (per user direction)

These are NOT pre-decided in discovery — they become discovery-during-build tasks during PoC, calibrated against real data:

1. **Tag taxonomy** — seed 10 tags, iterate at Milestone 3 against ~100 classified postings.
2. **LLM model choice** — benchmark local Ollama vs GPT-4o-mini at Milestone 3.
3. **PR/citizenship keyword list** — start with seed, grow organically.
4. **Exact similarity thresholds** — calibrated at Milestone 2 against hand-labeled data.
5. **Fit-score threshold** — calibrated at Milestone 3 against hand-labeled data.
6. **Coverage gaps** (additional search keywords, new sources) — identified during Milestone 4 based on real-use.

---

## 13. Commercial positioning

**Personal-first.** Commercial optionality explicitly re-evaluated at Beta transition by market-analyst. See MARKET-ANALYSIS.md (Step 2).

**Rationale**: user is actively job-searching and urgency is high; commercial-first would delay usable output by months. Market is crowded (Huntr, Teal, Simplify, JobScan). A defensible commercial thesis requires validation from real daily use, which this PoC will produce.

---

## 14. Out-of-scope (explicit)

- Auto-apply to postings on user's behalf
- CV rewriting / LLM-generated CVs (only selection from 5 variants)
- Mobile app / push notifications
- Multi-user / multi-tenant infrastructure
- Cloud hosting
- Commercial distribution (deferred to Beta review)
- French-language postings (deferred to MVP)
- Google for Jobs, Monster, Wellfound, aijobs.net, Greenhouse/Lever (deferred pending PoC coverage review)
- Interview prep / application-tracking beyond basic state
- Salary negotiation or offer comparison

---

## 15. Open items for downstream discovery

- **market-analyst** (Step 2): Commercial viability re-validation, competitor matrix (Huntr / Teal / Simplify / JobScan / LazyApply), positioning implications for Beta decision.
- **ux-designer** (Step 3): UX-SPEC.md for the single web surface — three-view layout, card design, keyboard shortcuts for quick dismiss, empty-state and error-state handling. Claude Design Brief for the main page.
- **architect** (Step 4): ROADMAP.md with phase boundaries + PoC milestone decomposition + exit criteria per phase.
