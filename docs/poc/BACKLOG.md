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

### MVP-M1 — Inactive AND Expired state lifecycle (supersedes auto-remove model)

**Decision date**: 2026-04-25 (Inactive); 2026-04-26 (Expired sibling concept added)
**Approved by**: User (Option A — full capture; Expired added 2026-04-26 from M1-005b real-data validation)
**Alignment verdict**: ALIGNED (see ALIGNMENT-LOG.md 2026-04-25 entry; 2026-04-26 entry for Expired)

**What**:
Replace the original "auto-remove after 90 days of silence" model with an Inactive state model, plus a sibling `Expired` state for hydrator-detected dead-link postings:
1. New status value: `Inactive`. Auto-trigger after ~90 days of silence on `status_updated_at` for `Applied`/`Screen`/`Interview` only (`Offer`/`Rejected`/`Withdrew` exempt).
2. Inactive entries stay forever in Applied tab as forensic history; user can manually transition Inactive → any status.
3. Dedup bypass: Inactive entries are treated as non-existent for BOTH URL-based and LLM content-based dedup. A new posting matching the same role surfaces on Main with a fresh posting_id; old Inactive entry persists.
4. **Expired status**: hydrator-detected dead-link postings transition to `status='Expired'` automatically (HTTP 404 from LinkedIn/Indeed). Same dedup-bypass mechanic as Inactive — reposts surface as fresh on Main, old Expired entry persists as forensic history.

**Why**:
- Auto-remove destroys forensic context (compensation, role details) the user may want for re-application context
- Silence ≠ dead: large-company hiring windows often exceed 3 months
- HR repost = real signal that role is still open and worth re-applying
- More semantically precise version of what auto-remove was attempting to do
- Dead-link postings: Dismiss semantically wrong (user wants to evaluate reposts); Expired = "system unavailable" not "user uninterested"; preserves repost-surfacing for legitimate role re-openings

**Schema impact for M1: NONE.**
`status` and `status_updated_at` columns already exist on `applied` table. `auto_remove_at` column is semantically dead from inception — see TDD §1.2a / §C7 superseded notes. Expired adds another allowed `status` value at MVP-M1 — no new column.

**Scope at MVP-M1**:
1. Schema: extend `status` allowed values to include `Inactive` AND `Expired` (and the rest of the funnel — `Screen`, `Interview`, `Offer`, `Rejected`, `Withdrew`). No new columns.
2. State manager (C7): replace `auto_remove_stale_applied()` with `auto_inactivate_stale_applied()` (sets `status='Inactive'`); add `update_status(posting_id, new_status)` that resets `status_updated_at`; **add `mark_expired(posting_id)` for hydrator-triggered transitions to `status='Expired'`**.
3. Dedup (C5/C6): both URL-based and LLM content-based dedup add `WHERE NOT EXISTS (… applied.status IN ('Inactive', 'Expired'))` semantics. **Both Inactive AND Expired entries are treated as non-existent for dedup purposes.**
4. Scheduler (already MVP-M1 scope): daily cron/launchd job runs `auto_inactivate_stale_applied()`. (No scheduler needed for Expired — it's hydration-triggered, not time-triggered.)
5. UI (C8):
   - Applied tab gains Inactive section/filter
   - **Dismissed tab gains Expired section/filter** (or, at MVP-M1 planning, decide if a unified "Unavailable" filter spanning Inactive + Expired is cleaner)
   - Main tab indicates entries whose URL once mapped to an Inactive OR Expired posting (e.g. "Reposted" badge)
6. **Hydrator (C5/C6) auto-detect**:
   - On hydration, if HTTP response is 404 (or "this job is no longer available" markers), call `mark_expired(posting_id)` — the posting transitions to `Expired` automatically, no user action required
   - Other failure modes (403, 500, network timeout) remain `hydration_status='failed'` — those are transient, not expired

**Out of scope for this item (separate MVP item)**:
- Inactive accumulation reminder notification (UI prompt when Inactive count crosses threshold). Logged separately because Inactive entries never auto-remove and could accumulate over years.
- Manual "Job link is dead" button on cards — deferred to MVP-M2; auto-detect via hydrator 404 covers the common case at zero user effort

**Caveats to action at MVP-M1 planning**:
1. Confirm `status_updated_at` is written on every status transition (not just initial `apply`) — this is the silence clock.
2. The dedup bypass applies to both URL-based (M1/M2) and LLM-based (MVP) dedup — explicit in PRD §5 M2 update; do not let the URL path slip through unmodified.
3. Decide whether to drop or repurpose the `auto_remove_at` column at MVP-M1 (it's dead-code in M1; either remove it or leave as a vestigial column — small migration either way).
4. **Status enum reconciliation**: TDD §1.2a currently documents the `applied.status` enum as `Applied / Screen / Interview / Offer / Rejected / Ghosted`. The new design introduces `Inactive` as the auto-transitioned-when-cold state, which is the concept the original `Ghosted` placeholder was likely standing in for. The MVP-M1 enum should resolve to: `Applied / Inactive / Screen / Interview / Offer / Rejected / Withdrew` — adding `Inactive` (system-set), renaming/dropping `Ghosted`, and adding `Withdrew` (genuinely missing terminal status for user-initiated pull-out). Decide and update TDD §1.2a at MVP-M1 planning.
5. **Status enum reconciliation now also includes Expired**: TDD §1.2a `applied.status` enum should resolve at MVP-M1 to `Applied / Inactive / Expired / Screen / Interview / Offer / Rejected / Withdrew`. (Update of caveat #4.)

**M1 workaround for dead links**: until MVP-M1 lands the Expired status, users encountering a dead link should click Dismiss. Limitation: if the same role is reposted with the same `jk=`, dedup will suppress it; if reposted with a new `jk=`, user will see what looks like a "new" job and may be confused. Acceptable trade-off for M1 — proper Expired handling fully addresses both cases at MVP-M1.

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
