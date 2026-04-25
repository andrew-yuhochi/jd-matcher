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
