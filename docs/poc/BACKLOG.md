# Backlog — jd-matcher — PoC

> **Phase**: PoC
> **Last Updated**: 2026-04-24

Items here are explicitly deferred — either to a later PoC milestone (M2/M3/M4), to MVP, or to Beta. Each entry includes the deferral rationale so a future reader can audit the decision.

---

## Deferred to PoC M2 — Content-aware dedup

- **Cross-source content-aware dedup** (LLM-extracted-fields + JD-embedding fusion). Requires C5 hydrator + LLM extraction (M3) — but content-only dedup using JD embeddings can land in M2 without LLM extraction.
- **Repost detection** (same JD reposted under new jobId after 30+ days).
- **Block-key composition refinement** (`canonical_company`, `canonical_seniority`, `canonical_location`) — depends on either rule-based normalization (M2) or LLM-extracted fields (M3, preferred).

---

## Deferred to PoC M3 — Smart layer (LLM extraction + classification)

- LLM extraction call producing fit_score, tags, salary, dedup fields, industry, PR-required flag, Canadian-employer-likelihood.
- Hard filters (location / seniority / PR keywords) — wired in M3 once LLM extraction is producing the fields.
- Soft ranking (salary + industry + recency).
- `classify-always-filter-configurably` principle — store every classification regardless of filter state (commercial hedge 1).
- Tag taxonomy review task — refine seed taxonomy after classifying ≥100 real postings.
- Local-Ollama vs cloud-LLM benchmark (optional sub-task in M3 — defaults to cloud per user direction).

---

## Deferred to PoC M4 — CV recommender + extended sources + analytics

- **CV variant recommender**: 5-CV ranking via cosine similarity between role embeddings and CV embeddings.
- **Job Bank Canada email alerts** ingester (user has not yet set up alerts; will activate at M4).
- **Himalayas API** client (free, structured, ≥93 Canadian DS results live-tested).
- **Remotive API** client (`category=ai-ml` filter).
- **Jobicy API** client.
- **HN "Who is Hiring"** RSS parser.
- **Analytics view** (FastAPI Jinja2 page at `/analytics`, three HTML tables: session summary, daily breakdown, source contribution) — reads from the events table populated since M1.
- **CV settings page** activation (5 CV slot UI exists from M1 as stub; activated at M4 when recommender lands).

---

## Deferred to MVP

- **Scheduling** — launchd job for unattended pipeline runs.
- **Gmail OAuth refresh-token automatic recovery** — startup health check + clear error UI for expired tokens.
- **French-language postings** — French-capable embedding model (`paraphrase-multilingual-MiniLM-L12-v2`); French parser tweaks.
- **Dismissal-reason categories** + UI dropdown on dismiss action.
- **Weekly review surface** — aggregates dismissal reasons + proposes threshold/keyword tuning.
- **Settings page expansion** — fit-threshold slider, ranking-weight controls, source toggles.
- **`scheduler` for `auto_remove_stale_applied`** — cron-like trigger to remove applied entries unchanged for 3 months.
- **Coverage expansion based on PoC gaps** — additional LinkedIn search keywords (`AI Engineer`, `Applied AI Research`, `Quant Research`); Greenhouse ATS curated employer list (if PoC coverage audit reveals gap).
- **Per-user namespace utilization** — schema is namespace-aware from M1 (hedge 3) but `user_id='default'` is the only value through MVP.

---

### MVP-M1 — Inactive state lifecycle (supersedes auto-remove model)

**Decision date**: 2026-04-25
**Approved by**: User (Option A — full capture)
**Alignment verdict**: ALIGNED (see ALIGNMENT-LOG.md 2026-04-25 entry)

**What**:
Replace the original "auto-remove after 90 days of silence" model with an Inactive state model:
1. New status value: `Inactive`. Auto-trigger after ~90 days of silence on `status_updated_at` for `Applied`/`Screen`/`Interview` only (`Offer`/`Rejected`/`Withdrew` exempt).
2. Inactive entries stay forever in Applied tab as forensic history; user can manually transition Inactive → any status.
3. Dedup bypass: Inactive entries are treated as non-existent for BOTH URL-based and LLM content-based dedup. A new posting matching the same role surfaces on Main with a fresh posting_id; old Inactive entry persists.

**Why**:
- Auto-remove destroys forensic context (compensation, role details) the user may want for re-application context
- Silence ≠ dead: large-company hiring windows often exceed 3 months
- HR repost = real signal that role is still open and worth re-applying
- More semantically precise version of what auto-remove was attempting to do

**Schema impact for M1: NONE.**
`status` and `status_updated_at` columns already exist on `applied` table. `auto_remove_at` column is semantically dead from inception — see TDD §1.2a / §C7 superseded notes.

**Scope at MVP-M1**:
1. Schema: extend `status` allowed values to include `Inactive` (and the rest of the funnel — `Screen`, `Interview`, `Offer`, `Rejected`, `Withdrew`). No new columns.
2. State manager (C7): replace `auto_remove_stale_applied()` with `auto_inactivate_stale_applied()`; add `update_status(posting_id, new_status)` that resets `status_updated_at`.
3. Dedup (C5/C6): both URL-based and LLM content-based dedup add `WHERE NOT EXISTS (… applied.status='Inactive')` semantics.
4. Scheduler (already MVP-M1 scope): daily cron/launchd job runs `auto_inactivate_stale_applied()`.
5. UI (C8): Applied tab gains Inactive section/filter; Main tab indicates entries whose URL once mapped to an Inactive posting (e.g. "Reposted" badge).

**Out of scope for this item (separate MVP item)**:
- Inactive accumulation reminder notification (UI prompt when Inactive count crosses threshold). Logged separately because Inactive entries never auto-remove and could accumulate over years.

**Caveats to action at MVP-M1 planning**:
1. Confirm `status_updated_at` is written on every status transition (not just initial `apply`) — this is the silence clock.
2. The dedup bypass applies to both URL-based (M1/M2) and LLM-based (MVP) dedup — explicit in PRD §5 M2 update; do not let the URL path slip through unmodified.
3. Decide whether to drop or repurpose the `auto_remove_at` column at MVP-M1 (it's dead-code in M1; either remove it or leave as a vestigial column — small migration either way).

**M1 status**: TASK-M1-007 stands as shipped. No M1 changes required.

---

## Deferred to Beta (decision gate)

- **Variant A (stay personal)**: durability hardening, runbook, 6-month stable use validation.
- **Variant B (commercial pivot)**:
  - Multi-tenant rewrite (activate the `user_id` namespace).
  - Ingestion overhaul — LinkedIn ToS-clean architecture (email-only at scale; HiQ Labs precedent rules out current guest-endpoint hydration commercially).
  - Open-source + paid managed-tier distribution model.
  - Hand-labeled benchmark extended from 30 → 100 postings (user explicitly moved this out of PoC; pre-Beta task).
  - Three personas articulated outside DS to widen TAM beyond Canadian DS niche.

---

## Out-of-scope items raised but not pursued

- **Auto-apply to postings on user's behalf** — out of scope (PRD §6); user retains manual control.
- **CV rewriting / LLM-generated CVs** — out of scope (PRD §6); only selection from 5 user-provided variants.
- **Mobile app / push notifications** — out of scope (PRD §6); local-only desktop tool.
- **Cloud hosting** — out of scope for PoC + MVP; revisit only if Beta Variant B is chosen.
- **Direct company career-page scraping** — deferred indefinitely (per-site maintenance cost too high).
- **Google for Jobs / SerpAPI** — deferred to MVP if coverage gap emerges; paid tier breaks personal-use budget.
- **Monster Canada** — coverage too thin for Canadian DS; permanently dropped.
- **Wellfound (AngelList)** — no official API path + weak Canadian coverage; permanently dropped.
- **aijobs.net** — RSS/alerts behind $17/mo paywall; deferred indefinitely.
