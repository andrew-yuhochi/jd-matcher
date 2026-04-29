# Backlog — jd-matcher — PoC

> **Phase**: PoC
> **Last Updated**: 2026-04-29

Items here are explicitly deferred — either to a later PoC milestone (M2/M3/M4), to MVP, or to Beta. Each entry includes the deferral rationale so a future reader can audit the decision.

---

## Deferred to PoC M2 — Content-aware dedup

- **Cross-source content-aware dedup** (LLM-extracted-fields + JD-embedding fusion). Requires C5 hydrator + LLM extraction (M3) — but content-only dedup using JD embeddings can land in M2 without LLM extraction.
- **Repost detection** (same JD reposted under new jobId after 30+ days).
- **Block-key composition refinement** (`canonical_company`, `canonical_seniority`, `canonical_location`) — depends on either rule-based normalization (M2) or LLM-extracted fields (M3, preferred).

---

## Promoted to TASK-M2-012 scope — LLM gatekeeper for all merges

### LLM dedup gatekeeper using full job descriptions

**Surfaced**: 2026-04-29 — TASK-M2-008 edge-case validation
**BA verdict (initial)**: DRIFTING (logged in ALIGNMENT-LOG.md 2026-04-29 entry — original "fallback for borderline" framing)
**User decision (initial)**: 2026-04-29 — accepted BA Option A: defer to TASK-M2-012, re-evaluate based on fuzzy-zone hit rate
**User decision (refined, 2026-04-29 same-session)**: sharpened design + promoted to TASK-M2-012 scope unconditionally. No re-evaluation gate — build the gatekeeper as part of TASK-M2-012 calibration work.

**Two-tier merge decision rule**:
- **Tier 1**: FUSE total ≥ 0.75 → LLM gatekeeper required (reading FULL JDs); merge only if LLM confirms "same role at same employer"
- **Tier 2**: FUSE total < 0.75 → no merge (default)

**Why this design (vs the original "fallback for borderline 0.85–0.95")**:

1. **Asymmetric cost recognition** — for a job-search tool, under-merge (apply twice = wasted ~10 min, recoverable) is dramatically cheaper than over-merge (silently hide a real opportunity = unrecoverable). Conservative bias toward keeping-both is correct.

2. **Full JD as ground truth** — `role_summary` is an LLM compression that introduces noise. Saw this concretely in Alignerr 66↔67 (TASK-M2-008 edge-case validation): same Alignerr contract role posted under "Engineer" vs "Expert" titles produced inconsistent role_summary phrasings AND inconsistent skill extractions (2 vs 5 skills), depressing FUSE total to 0.714. A full-JD LLM read bypasses this compression-loss issue.

3. **Gatekeeper semantics match the cost model** — LLM must actively say "yes, same role" to permit merge. Silence or uncertainty defaults to no-merge. This operationalizes "under-merge > over-merge" cleanly.

4. **No auto-merge bypass even for byte-identical pairs** — every merge requires LLM approval. Defense against degenerate edge cases (e.g., a future bug producing zero-vector embeddings or hash collisions silently scoring 1.000). Trivial cost saved by bypassing the obvious dups (~$0.007/week) isn't worth the special-case branching complexity.

**Trade-off explicitly accepted by user**: pairs scoring 0.70–0.749 (e.g., **Alignerr 66↔67 at 0.714**, our strongest example of an under-merge in the corpus) will NOT trigger the LLM gatekeeper and will stay separate. This is the user's accepted under-merge cost in exchange for a clean two-tier rule.

**Implementation (now in TASK-M2-012 scope, see TASKS.md TASK-M2-012 ACs)**:
- New component: `LLMDedupClassifier` (C28-style provider-abstracted, parallel to existing extraction provider)
- New prompt: `prompts/dedup_classifier_v1.txt` — pair of FULL JDs + titles + companies in, yes/no + brief reasoning out
- C21 integration: in `decide()`, when `total_similarity ≥ 0.75`, dispatch to classifier; classifier verdict is the final merge gate (overrides the FUSE-derived candidate decision)
- Gate 4 implication: dedup decision is probabilistic for Tier-1 pairs (~25% of all decisions in current corpus). Per-merge LLM verdict + reasoning logged for user audit.

**Cost estimate (validated against current corpus)**: ~11 of 44 within-block pairs (25%) score ≥ 0.75 → ~$0.001/call × 11 = **~$0.011 per pipeline run**. Negligible.

**Latency**: +1-2 seconds per gatekeeper-eligible pair. Acceptable for nightly batch; does not impact interactive UX (dedup runs in pipeline, not at view-time).

**Why DRIFTING was the right initial verdict but the refined design is defensible to ship**:
- PRD §5 M2 confines C18 LLM to normalisation; this proposal adds a SECOND LLM call (classification) to C21
- The refined design honors the BA's recommendation that calibration is the right gate — building the gatekeeper as part of TASK-M2-012 means it ships with empirical justification (the calibration data shows where the FUSE math falls short)
- The two-tier rule is bounded and auditable (single threshold, single LLM call per Tier-1 pair)
- M3 already opens the LLM scope to full classification per PRD; this is a small early step in that direction, contained inside one component (C21)

**Pattern note**: Third M2 proposal to expand the LLM layer beyond normalisation (after `role_orientation` deferred to M3 + the full_jd-fallback safety check added defensively at M2-008). User's repeated direction that LLM enrichment in M2 is acceptable when the use case justifies it is now an established pattern — worth checking against PRD §5 boundaries explicitly at /milestone-complete.

---

## Deferred to PoC M3 — role_orientation classification field

### PoC-M3 — `role_orientation` classification field (Engineering / Problem-Solving / Communication)

**Decision date**: 2026-04-29
**Approved by**: User (BA verdict DRIFTING; user chose Recommendation B — defer to M3)
**Source**: TASK-M2-006b Phase B 2026-04-29 — BA verdict DRIFTING, user chose defer
**Status**: Parked
**Target phase**: M3

**What**: Add a new field to the C18 canonical extraction at M3:

```
role_orientation: list[str]   # 1–3 items, each from
                              #   {Engineering | Problem-Solving | Communication}
```

Multi-select; captures mid-senior IC roles that span 2–3 archetypes.

**Definitions**:
- Engineering — executor: builds and ships systems / pipelines / models
- Problem-Solving — researcher: designs methods to solve identified problems
- Communication — consultant: works with stakeholders to discover bottlenecks and propose ideas

**Rationale (why M3 not M2)**: `top_skills` must stay purely technical for clean FUSE Jaccard semantics. `role_orientation` is a first-class role attribute (not a technique). M3 already expands the C18 prompt for full classification (tags / primary_focus / fit_score / fit_reasoning); `role_orientation` slots in there with a natural AC.

**Downstream uses**:
- C21 FUSE small-weight term (~+0.05 × orientation_jaccard) — different orientations within same team are genuinely different roles
- M4 CV recommendation: match posting orientation to user's CV variants
- Web UI: tag posting card with orientation chip
- MVP+ filtering: "show me engineering-heavy roles only"

**Implementation cost at M3 (~100 LOC)**:
- `ALTER TABLE postings ADD COLUMN role_orientation TEXT` (JSON list)
- Pydantic field on `CanonicalExtraction` with len-1-to-3 validator
- New `=== ROLE ORIENTATION ===` section in `canonical_extraction_v1.txt` with definitions + few-shot examples
- 5 hand-crafted synthetic JDs with known orientation labels for regression
- Re-extraction at M3 picks up the field automatically

**AC (at M3)**: ≥80% label agreement on the M3 30-posting hand-label set (same set that gates SC-9 and SC-10).

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
- **Himalayas API** client (free, structured, ≥93 Canadian DS results live-tested) — **see "PoC-M4 — Himalayas API source (deferred from M2)" entry below for the deferral rationale**.
- **Remotive API** client (`category=ai-ml` filter).
- **Jobicy API** client.
- **HN "Who is Hiring"** RSS parser.
- **Analytics view** (FastAPI Jinja2 page at `/analytics`, three HTML tables: session summary, daily breakdown, source contribution) — reads from the events table populated since M1.
- **CV settings page** activation (5 CV slot UI exists from M1 as stub; activated at M4 when recommender lands).

---

### PoC-M4 — Himalayas API source (deferred from M2)

**Decision date**: 2026-04-27
**Approved by**: User (during /milestone-plan for M2)

**What**: Add Himalayas API as a fourth posting source (after LinkedIn email, Indeed email, and Indeed pagead resolution). Per RESEARCH-REPORT.md §5, Himalayas exposes ≥90 Canadian DS roles with a clean public API — meaningful additional coverage for a Vancouver DS/ML job-hunter.

**Why deferred from M2**: M2 is the content-aware dedup milestone (LLM extraction + embeddings + two-stage matching). Himalayas adds a new source axis (API client + parser + integration with the dedup pipeline) that's orthogonal to the dedup work. Bundling source-expansion together at M4 keeps M2 focused on the technique milestone and matches M4's existing planned multi-source expansion (Job Bank, Remotive, Jobicy, HN per ROADMAP §M4).

**M4 placement rationale**: ROADMAP §M4 already plans 4 new sources (Job Bank Canada, Remotive, Jobicy, HN). Himalayas joins as the 5th — same shape (parser, hydrator, source-health badge, integration tests), same code area, same effort pattern. ROADMAP wording will need a one-line update at M4 planning time (currently presupposes Himalayas is in pre-M4).

**Caveats at M4 planning time**:
- Himalayas API rate limits — confirm at M4 planning vs current docs
- Himalayas content format — does it expose `role_summary` directly or do we still need LLM extraction? (Affects M2 dedup engine integration)
- Cross-source dedup with Himalayas — will join naturally with M2's content-dedup; no new mechanism needed

**Tests blocked**: M2's "≥3 real cross-source pairs" AC works fine on LinkedIn↔Indeed pairs alone (no Himalayas needed). M2 closure not blocked.

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

### MVP-M1 — Sync progress feedback

**Decision date**: 2026-04-25
**Approved by**: User (during M1-010 real-data testing — explicit "add to BACKLOG, not TASKS")

**What**:
Surface real-time progress during pipeline sync runs so the user knows what's happening during the 30+ minute sync window. Currently the UI shows no visible progress between clicking "Run sync now" and the eventual completion — sub-bar source badges only flip color AFTER each source fully completes; there is no per-URL or per-step granularity exposed to the UI.

**Why**:
Real-data sync against ~50–90 URLs takes 30–40 min due to TDD §1.4 rate limit (1 req / 30s for hydration). Without progress feedback, the user can't distinguish "still working" from "stuck" — leads to repeated clicks (creating concurrent runs and DB lock contention) or premature giving-up. The orchestrator already emits step-progress strings (per UX-SPEC.md §5: "Fetching Gmail (1/4)…", "Hydrating JDs (2/4)…") but these never reach the UI.

**Schema impact for M1: NONE.** This is a deferred MVP-M1 item — no schema or behavioural change at PoC M1.

**Scope tiers** (MVP-M1 picks the appropriate tier based on user value vs implementation cost):

1. **Lightweight (recommended default for MVP-M1)**:
   - Status text under sub-bar: "Syncing… gmail_linkedin ✓, gmail_indeed running, hydrator queued"
   - Reuses existing TDD §C11 step-progress strings already emitted by orchestrator
   - Client polls `/api/source-health` every 2–5s during active sync
   - Detect "active sync" via the latest `pipeline_run` row's `finished_at IS NULL` state
   - Stops polling when all 4 sources show `finished_at NOT NULL`

2. **Medium (opt-in)**:
   - Per-URL progress bar: "Hydrating 23 of 91 URLs… 5 min remaining (12s/URL avg)"
   - Stream events via Server-Sent Events (SSE) endpoint `/api/sync/events`
   - New event types in the existing `events` table for sync-step granularity
   - Client subscribes to SSE feed during active sync, updates progress bar in real-time

3. **Heavy (deferred to MVP-M2 or later)**:
   - Live-updating card list: cards appear on Main as they finish hydrating (vs all-at-once after sync)
   - WebSocket connection
   - Reactive UI updates per posting state change

**Caveats to action at MVP-M1 planning**:
1. The orchestrator's step-progress strings exist (TDD §C11 Responsibility 5) but currently only appear in JSON logs. The Lightweight tier needs the orchestrator to also write step-progress events to the `events` table OR a new ephemeral table.
2. Polling at 2–5s during a 30-min sync = ~360–900 polls per sync. Acceptable at personal-use scale but the client must NOT poll continuously when no sync is active. Default state: no polling.
3. The Medium tier (SSE) is a real architectural addition — new transport, new client subscription logic. Worth scoping carefully at MVP-M1 planning vs deferring to MVP-M2.

**Out of scope for this item**:
- Mobile or non-browser progress views — covered separately by Beta-scope items.
- Sync history view ("show me last 7 days of sync runs") — partially covered by `M1-005c` report CLI; a UI surface for it is a separate MVP-M1 item.

**M1 workaround** (until MVP-M1 lands progress display):
User can monitor sync progress via:
- `tail -f ~/.jd-matcher/logs/pipeline-<run_id>.jsonl` — live JSON event stream
- `sqlite3 ~/.jd-matcher/jd-matcher.db "SELECT source, health_status, started_at, finished_at FROM pipeline_runs ORDER BY started_at DESC LIMIT 4;"` — current run state

Acceptable trade-off for M1 since the rate limit makes long syncs unavoidable; the MVP scheduler + progress display is the right place for this UX investment.

---

### MVP-M1 — Filtered Postings tab UI

**Decision date**: 2026-04-27
**Approved by**: User (during /milestone-plan for M2)

**What**: New "Filtered" tab in the web UI alongside Main / Applied / Dismissed. Lists postings that were dropped by C19 (title-based interest filter) with the matched deny pattern shown as a small chip on each card. Each card has a "Rescue" button that adds an exception to `config/title_filters.yaml` so the posting flows through on the next sync.

**Why**: M2 ships with C19 dropping postings invisibly — the audit trail lives only in `email_ingest_log.filter_status='filtered'` and is surfaced by the `python -m jd_matcher.report ingest --filtered` CLI flag. Audit-trail-only UX is fine for M2 development cycle but not user-friendly long-term — the user has to inspect a CLI to know what's been filtered. A UI tab makes false-positive review natural and lets the user iteratively tune the filter without leaving the browser.

**Why deferred from M2**: M2's user-observable deliverable is content-aware dedup (multi-source cards + Reposted badge per ROADMAP §M2). The Filtered tab is observability for a different feature (C19 cost-optimisation filter) and would add UI scope creep that competes for the same M2 implementation window. The audit trail in `email_ingest_log` + `report ingest --filtered` CLI is sufficient for M2 development and calibration. Promote to MVP-M1 once the dedup feature is stable AND the user has had a few weeks of real-data filter operation to confirm the filter design holds.

**Schema impact for M1: NONE.** The `email_ingest_log.filter_status` and `filter_reason` columns ship in M2 (TDD §1.2a M2 schema delta). The optional richer `title_filter_decisions` table was rejected for M2; if the Filtered tab needs richer per-event analytics at MVP-M1 (e.g. timestamp of each filter event independent of email arrival), this is the right time to add it.

**Implementation outline**:
- New `/filtered` route + Jinja2 template (mirrors the existing `/applied` and `/dismissed` patterns from C8)
- New backend endpoint `POST /postings/rescue` taking `{gmail_message_id, title}` — modifies `config/title_filters.yaml` to add an allow-pattern entry for the title (or removes the matching deny pattern, depending on UX design at planning time)
- Card rendering: title (deny pattern chip), source, received-at; same compact density as Dismissed cards
- New `btn-rescue` button on filtered cards with confirm dialog
- Same keyboard shortcuts as Dismissed tab (`e` to expand, `o` to open URL on the source platform if hydration was attempted before filtering — N/A for C19 since filter happens pre-hydration; consider showing "(no JD fetched)" instead)
- Sub-bar count badge: `Filtered (N)` next to `Main / Applied / Dismissed`

**Caveats to action at MVP-M1 planning**:
1. **Rescue semantics** — the YAML edit is delicate: an allow-pattern that's too broad un-filters all similar titles, not just the one rescued. UX design at MVP-M1 must decide between (a) per-title exact-match allow pattern (precise but bloats YAML), (b) prompt the user to write a regex (powerful but error-prone), or (c) just remove the matched deny pattern (broad — affects the whole filter config).
2. **Rescue re-triggering** — after a rescue, the original email's URLs need to be re-extracted on the next sync to flow through. C4 currently re-parses every email it sees in Gmail (no email-level dedup), so this works naturally — confirm at MVP-M1 planning.
3. **Filter config versioning** — `config/title_filters.yaml` edits via the Rescue button should be version-controlled or at least timestamped (a comment header like `# Last edited via Rescue UI: 2026-XX-XX HH:MM, restored "Backend Engineer (Data Platform)"` is the lightweight option) so the user can audit what changed and revert.
4. **Empty-state UX** — first-time users with no filtered postings need an explainer ("No postings have been filtered yet. C19 silently drops obviously-irrelevant titles to save LLM cost — see config/title_filters.yaml for the active rules.") to avoid a confusing blank tab.

**Out of scope for this item**:
- Auto-suggest deny/allow patterns from filtered-vs-rescued history (ML on top of the user's rescue decisions) — interesting but a separate MVP-M2 candidate.
- Daily-emailed digest of filtered postings — covered by the existing M1 report CLI, no UI needed.

**M2 workaround** (until MVP-M1 lands the Filtered tab):
- `python -m jd_matcher.report ingest --filtered` (the M2 C27 extension) lists every filtered email + matched pattern
- To rescue: edit `config/title_filters.yaml` directly + re-run sync; the email's URLs are re-parsed by C4, re-tested by C19 (now passing), and flow normally into the M2 pipeline

Acceptable trade-off for M2 — the filter is new, deny patterns will need iteration, and editing a YAML file is a reasonable interim UX for the M2 calibration window.

---

### MVP-M1 — Indeed extraction via personal non-managed machine

**Decision date**: 2026-04-28
**Approved by**: User (during M2-006 calibration recovery — Indeed deferral decision)
**Alignment verdict**: DRIFTING but SOUND-WITH-CAVEATS (see ALIGNMENT-LOG.md 2026-04-28)

**Why deferred**: 2026-04-28 IP-level Cloudflare block on user's employer-managed Mac; CDP-attach Tier 2 blocked by MDM policy disabling `--remote-debugging-port`. All bypass paths failed (requests + Sec-Fetch headers, curl_cffi with Chrome impersonation, browser-cookie3 + cf_clearance injection, patchright headed + persistent profile). The hardware constraint is the blocker, not the code.

**MVP-M1 trigger**: user runs jd-matcher on a personal desktop (no MDM).

**Activation work**:
1. Enable `gmail_indeed` source in pipeline.py
2. Verify browser_fetcher Tier 1 (patchright) bypasses Cloudflare on residential IP from personal machine
3. If Tier 1 still fails, activate Tier 2 (CDP-attach) which is now policy-compatible (no MDM blocking `--remote-debugging-port`)

**Estimated effort**: 1 day (verification + integration smoke test on personal hardware)

**Reference**: browser_fetcher.py + indeed.py escalation logic committed at PoC M2.

---

### MVP-M1 — Indeed extraction via commercial proxy (alternative path)

**Decision date**: 2026-04-28
**Approved by**: User (during M2-006 calibration recovery — Indeed deferral decision)
**Alignment verdict**: DRIFTING but SOUND-WITH-CAVEATS (see ALIGNMENT-LOG.md 2026-04-28)

**Why deferred**: same root cause as the Personal-machine entry above, but addresses the case where personal machine is unavailable OR Cloudflare IP-block persists across networks (e.g., residential IP also flagged).

**MVP-M1 trigger**: Personal-machine path fails OR user explicitly opts for the proxy path.

**Activation work**:
1. Procure rotating residential proxy (Oxylabs / Bright Data / similar at ~$10-50/mo)
2. Wire into patchright `launch_persistent_context` proxy parameter
3. Validate Cloudflare bypass on proxied IP

**Estimated effort**: 0.5 day setup + ongoing $10-50/mo recurring cost.

**Reference**: same browser_fetcher.py infrastructure as the Personal-machine entry.

---

### MVP-M1 — browser_fetcher.py asset note (informational, NOT a new task)

**Status**: Committed at PoC M2 (commit SHA TBD after main session commits the infrastructure separately).

**Purpose**: Generic Playwright-based URL fetcher with two-tier escalation (patchright headed → CDP-attach to user's Chrome).

**Currently used by**: indeed.py auto-fallback on Cloudflare 403+Cf-Mitigated (currently always fails due to PRD §9 R3 realized risk on this hardware).

**MVP-M1 reactivation path**: see "Indeed extraction via personal non-managed machine" entry above OR "Indeed extraction via commercial proxy" entry above.

**Future MVP+ candidates**: any source that hits similar bot detection — Job Bank, alternative scraped sources, etc. The two-tier escalation pattern is source-agnostic and ready to wire into other hydrators when needed.

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
