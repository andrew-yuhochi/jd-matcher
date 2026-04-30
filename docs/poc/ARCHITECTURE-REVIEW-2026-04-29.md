# Architecture Review — jd-matcher PoC — 2026-04-29

**Trigger**: User directive at M2 close (BACKLOG `68440bc`) — review architecture before drafting M3 tasks.
**Scope**: Source-code architecture only (test-suite review in companion `TEST-SUITE-REVIEW-2026-04-29.md`).

---

## Executive summary

The codebase is in **good** shape after M2: the per-component boundaries from the TDD survived the milestone, the storage / pipeline / web layers stay decoupled, and dedup is properly factored into discrete pure-decision (engine), pure-write (merge), and side-channel (repost, classifier, calibrate) modules. The 982-test count is a function of the breadth of M2 (gatekeeper + 4-feature short-circuit + skills tiering UX + cost-watchdog + cache layers), not of architectural rot.

There is **one load-bearing data-flow bug masquerading as a vestigial-column issue**: `postings.canonical_seniority` was added by an M2 migration, but `LLM extract.py` never writes the LLM-extracted value back to `postings`. Both `dedup/engine.py` (line 560) and `dedup/merge.py` (line 60) still read the legacy `seniority_band` column for "the candidate's seniority". Because seniority is a 0.1-weight FUSE input and the gatekeeper sees the full JD anyway, this has not produced visible misbehavior on the small corpus — but it is the same pattern as the `extraction_cache → canonical_postings` propagation gap surfaced during M2-012 (BACKLOG line 198), and it will silently distort calibration. **HIGH-priority, small fix.**

The other two themes are housekeeping: `pipeline.py` at 1480 lines is doing too many things at once (orchestration + 6 phases of inline DB queries + 12 helpers — the file crossed the 500-line threshold in our discipline rules), and the TDD has accumulated 6 "M2 update" footnotes on C5/C7/C8/C9/C11/C21 that should be folded into the main entry bodies before M3 planning. Neither is urgent; both should be done before M3 implementation starts so M3 doesn't compound them.

---

## 1. Module boundaries + coupling

| Module | LOC | Responsibility | Notes |
|---|---|---|---|
| `pipeline.py` | **1480** | Orchestrator (C11) | **Largest file in the repo by 60%+.** Contains 7 phases inline (gmail × 2, hydrator × 2, extraction, embedding, dedup+merge), 12 private DB helpers (`_get_pending_*`, `_count_*_since`, `_sum_*_since`), per-source runners, `_setup_run_logger`, `_emit_transition_event_if_needed`, and `_get_monthly_llm_cost`. Phase-3/4/5 ledger-counting helpers are 9 near-identical functions that select-aggregate over `llm_call_ledger` with a `before_id` cursor. **Refactor candidate.** |
| `dedup/calibrate.py` | 905 | C32 calibration CLI | Standalone script; not imported anywhere except `dedup/__main__.py`. Size acceptable: it is a one-off CLI report generator, not runtime code. **Keep as-is.** |
| `dedup/engine.py` | 808 | C21 BLOCK + FUSE + dispatch | `decide()` is ~300 lines; reasonable given 3-tier logic and the gatekeeper bridge. Reads `postings.seniority_band` (line 560) — see schema hygiene §4. |
| `llm/extract.py` | 663 | C18 extraction + cache + ledger | Three concerns interleaved: prompt build, transient/parse retry loops, cache R/W. Acceptable. **The smoking gun: `extract_canonical()` returns the `CanonicalExtraction` object but does NOT write it back to `postings`.** Only writes are: `extraction_cache` JSON blob, `llm_call_ledger`, and on failure `postings.extraction_status='failed'` + `fit_reasoning=raw_response`. See §2 + §4. |
| `llm/validate.py` | 639 | Validation CLI for extraction quality | Standalone, like calibrate.py. Acceptable. |
| `web/routes.py` | 576 | C8 endpoints | 9 endpoints + 5 helper functions. `_main_view_canonical_list` and `_aggregate_link_info` (in `state/canonical_view.py`) split cleanly. `_compute_all_tab_counts` added late in M2-013 is correctly internal to routes.py — not promote-worthy as a TDD component. |
| `state/canonical_view.py` | 466 | C22 + canonical card assembly | Reads-only API; SQL-heavy but cohesive. The `_aggregate_link_info` helper (~95 lines) does the per-canonical source-precedence dedup (`linkedin_email` vs `linkedin_hydrator` for the same posting). Internally consistent — not a refactor target. |
| `dedup/merge.py` | 418 | C29 INSERT/UPDATE for canonical_postings | Reads `postings.seniority_band AS canonical_seniority` (line 60) — see §4. |
| `state/manager.py` | 319 | C7 write API | Apply/dismiss/restore/unapply. Clean. |

**Coupling assessment**: no cross-layer leaks. Web does not import from dedup; dedup does not import from web; pipeline imports broadly (correctly — it's the orchestrator). The only smell is that `llm/embed.py:cosine` is imported by `dedup/engine.py` — semantically reasonable but creates a dedup → llm dependency. Keep.

---

## 2. Component drift (TDD vs implementation)

| Component | Drift | Action |
|---|---|---|
| **C18 (LLM Extraction)** | TDD §C18 says "Updates `postings.canonical_*`, `postings.team_or_department`, `postings.top_skills`, `postings.role_summary`, `postings.extraction_status='success'\|'failed'`." **Implementation does NOT update those fields.** Only `extraction_status='failed'` + `fit_reasoning` are written on failure. Success path stores into `extraction_cache` only. | **HIGH — implementation gap.** Add a `_write_postings_extracted()` helper paralleling `_write_postings_failed()`. Once added, `dedup/engine.py:560` and `dedup/merge.py:60` can stop reading `seniority_band` (see §4). |
| **C11 (Orchestrator)** | TDD says 4 sources (`gmail_*`, `hydrator_*`); implementation runs Indeed-disabled with comment block. M2 update added 2 more synthetic sources (`llm_extraction`, `embedding`, `dedup_c21`, `dedup_merge_c29`) — that's 4 more `pipeline_runs` row-types. Step labels still say `(1/4)` etc. | **MEDIUM** — fold the M2 phase-count into the TDD §C11 entry body, drop the "Drift decisions" header at top of `pipeline.py` once the log path is reconciled. |
| **C7 (State Manager)** | Has dead `auto_remove_stale_applied()` per the M1 superseded note. Documented; no code consumer. | **LOW** — leave per BACKLOG MVP-M1 plan. |
| **C8 (Web UI backend)** | M2 added 4 LLM-derived display fields + sources[] + skills strip + a `/postings/{id}/unapply` endpoint not in the original M1 endpoint table. M2-013 added `_compute_all_tab_counts` — internal helper; not promote-worthy. | **MEDIUM** — append `unapply` to the §C8 endpoint table, fold the 3 M2 footnotes into the main entry. |
| **C9 (Frontend)** | Has 4 stacked "M2 update" footnotes (014/015/016 + UI re-validation). The latest footnote on the role_summary teaser truncation explicitly retracts a prior decision. | **MEDIUM** — collapse 4 footnotes into a single consolidated "M2 final layout" body. |
| **C21 (Dedup)** | `decide()` is intact and matches TDD. The `merge_kind` enum has grown from `{new_canonical, content_dedup, repost}` to `{new_canonical, content_dedup (legacy), repost, exact_4f, gatekeeper_approved}`. `content_dedup` is now write-time-dead. | **MEDIUM** — TDD §C21/§C29 should declare `content_dedup` deprecated (kept readable for old rows) and document the live enum. |
| **C29 (Merge)** | Matches TDD; `_apply_merge` reads only `first_seen / last_seen / full_jd / sources_summary` from canonical and applies the documented rules — does NOT read the LLM-extracted fields from the candidate (because they are not on `postings`). The merge consequently cannot drift the canonical's seniority/title/etc. by design — but it also means a wrong seed posting locks the canonical. **Working as specified, but see C18 fix.** | **OK** |
| **C32 (Gatekeeper)** | Matches TDD; `pending_gatekeeper` action is wired through `apply_decision`. | **OK** |

---

## 3. Configuration sprawl

Current state — 6 YAML files under `config/`, 666 lines total:

| File | Loader | Owner | Notes |
|---|---|---|---|
| `dedup.yaml` | `dedup/engine.py:_load_dedup_config` + `dedup/repost.py:52` | C21 + C30 | **Two separate readers of the same file.** `auto_merge_threshold` field is documented as LEGACY/unused but still read into `DedupConfig`. |
| `llm.yaml` | `llm/providers/config.py:load_llm_config` | C18 + C20 + cost-watchdog | Uses Pydantic model + clean defaults pattern. |
| `title_filters.yaml` | `filter/title_filter.py` + `filter/validate.py` | C19 | Largest config (317 lines — contains the seed pattern set). |
| `user_profile.yaml` | `skills/__init__.py:load_user_profile` | C9 skills tiering | New in M2-016. |
| `skill_categories.yaml` | `skills/__init__.py:load_skill_categories` | C9 skills tiering | New in M2-016. Bi-directional alias map. |
| `saved-searches.yaml` | **Documentation only — never read by code** (only mentioned in `ingest/gmail.py:30` comment) | Reference doc | Should be moved to `docs/poc/SETUP.md` or kept as-is and clearly labeled. |

**Coherence**: each loader uses a different pattern — `dedup` does its own dataclass + manual yaml.safe_load + try/except, `llm` uses Pydantic, `skills` uses `lru_cache` + dict. `title_filters` validates via Pydantic. **Three different loading patterns for five live configs is too many.**

**Recommendations**:
1. Standardise on the `llm/providers/config.py` pattern (Pydantic + lru_cache + path-relative resolution + explicit defaults). LOW priority — works fine, just inconsistent.
2. **Remove `dedup.auto_merge_threshold` from the live config and the `DedupConfig` dataclass.** It is documented in `config/dedup.yaml` as LEGACY but `_load_dedup_config` still loads it into a dataclass field that no live code consumes. Removing avoids the next reader believing the threshold is live. MEDIUM priority — costs nothing to fix.
3. Move `saved-searches.yaml` content into `docs/poc/SETUP.md` (it's documentation, not config). LOW priority.

---

## 4. Schema hygiene

**The vestigial-column problem is actually a data-flow bug.**

`schema.sql` declares `postings.seniority_band TEXT` (line 25). The M2-009/M2-010 migration in `init_db.py:30-40` adds `postings.canonical_seniority TEXT NULL` because `dedup/merge.py` was originally written to reference it. **But:**

- `llm/extract.py` (the only producer of canonical seniority) **does not write** `canonical_seniority` to `postings`. The extracted value lives in `extraction_cache.canonical_extraction_json`.
- `dedup/engine.py:560` and `dedup/merge.py:60` both read **`seniority_band`** (the original column), aliasing it as `canonical_seniority` in SQL.
- `postings.canonical_seniority` (the migration-added column) is therefore **always NULL** in production — the ALTER TABLE adds the column, but no code writes it.

**Concretely: the dedup engine is using whatever `seniority_band` was set to at email-parse time** (likely NULL since email parser doesn't extract seniority either) — NOT the LLM-extracted seniority. Because seniority is only a 0.1 FUSE weight, this hasn't surfaced as visible misbehavior on the 148-canonical corpus. It will distort future calibration as soon as M3 starts comparing against LLM-extracted ground truth.

**This is the same pattern as the `extraction_cache → canonical_postings` propagation gap** the user flagged on Jobright canonicals 316/395/396/458 (BACKLOG line 198). Both arise from the same root cause: **C18 only writes to `extraction_cache`, never to `postings`.**

**Vestigial / cleanup items**:

| Item | Status | Action |
|---|---|---|
| `postings.canonical_seniority` (ALTER-added) | Always NULL — dead column | **HIGH**: either start writing it from `extract_canonical()` (preferred) and switch dedup readers to use it; OR drop the column and document `seniority_band` as the live one. The first is cleaner. |
| `postings.seniority_band` (original) | Live read by dedup but never written by LLM | After fix above, deprecate or drop. |
| `postings.embedding BLOB` | Per TDD §1.2a "Schema delta", reserved at M1 but never written; superseded by `posting_embeddings`. **Confirmed: schema.sql does not declare it.** Already cleaned. | **OK** |
| `postings.salary_min_cad / industry / fit_score / tags / primary_focus / requires_pr_or_citizenship / canadian_employer_likely / language_required` | Declared in schema, no producer at M2 (M3 scope) | Forward-compat — keep as-is. |
| `applied.status CHECK constraint` | `('Applied', 'Screen', 'Interview', 'Offer', 'Rejected', 'Ghosted')` — does NOT include `Inactive` or `Expired` | Engine.py and TDD reference Inactive/Expired forward-compat. The CHECK currently rejects them — load-bearing only at MVP-M1. **OK**, but flag at MVP-M1 entry. |
| `posting_canonical_links.merge_kind` enum | Schema is TEXT (no CHECK). Live values: `new_canonical`, `exact_4f`, `gatekeeper_approved`, `repost`. Old rows may have `content_dedup`. | **OK** — no CHECK constraint to update; readers tolerate both. |
| Migration logic in `init_db.py` | 4 separate `_ensure_*` helpers each ALTER one column | **LOW**: consolidate into a single `_apply_pending_migrations` if a 5th lands; otherwise fine. |

---

## 5. Documentation consolidation

**TDD Part 2 footnotes that should be folded into entry bodies (one consolidation pass before M3 planning)**:

- **§C2 (Schema)**: M2 update note (line 559) — fold into Data stored row.
- **§C5 (JD Hydrator)**: M2 update note (line 610) — fold into Responsibility, since it changes the downstream contract.
- **§C7 (State Manager)**: M2 update note (line 642) — load-bearing canonical-id-keyed semantic; should be in main body.
- **§C8 (Web UI backend)**: M2 update note (line 675) + missing `unapply` endpoint — fold into endpoint table.
- **§C9 (Frontend)**: 4 stacked footnotes (M2-014, M2-015, M2-016, M2-015 re-validation). The re-validation note explicitly retracts the M2-015 truncation rule. Collapse all four into a single "M2 final layout" subsection; the retraction story is interesting only in commit history, not in TDD.
- **§C11 (Orchestrator)**: M2 update note (line 732) — explains the 4 new `pipeline_runs` source rows. Fold into Data stored.
- **§C19 (Title filter)**: leading italic note about Iteration 4 — already inline; keep.
- **§C21 (Dedup)**: schema-spec footnote about seniority moving from BLOCK to FUSE is actually load-bearing context — keep inline but cross-reference §1.2a.

**Other doc drift**:

- **TDD §1.2a "Schema delta — `postings.embedding`"**: schema.sql does not declare the column (already dropped). Note can be marked "resolved at M1" or removed.
- **TDD §1.6 Configuration**: lists fields under a single `config.yaml` (e.g., `dedup.auto_merge_threshold`, `filter.fit_threshold`) but the actual repo has 5 separate files. Update to reflect per-component YAMLs.
- **DATA-SOURCES.md**: Indeed deferral is consistently noted (line 92, line 16 implicit) — **OK, no drift**.
- **PRD.md** vs delivered work — flag separately during M3 PRD review; this audit is architecture-only.

---

## 6. Cross-cutting concerns

**State manager API (C7 + C22)**: clean. C7 stays write-only; C22 stays read-only. The apply-one-suppress-all behavior is implemented as a read-side `NOT EXISTS` join, not a write-time propagation — simpler and harder to corrupt. **Keep.**

**Pipeline orchestrator (C11) structure**: this is the one piece that grew unwieldy at M2. `run_pipeline()` is ~530 lines (lines 125–657) and contains 7 inline phases. Each phase has near-identical structure: `try { do work; write pipeline_runs(healthy) } except { write pipeline_runs(failed) }`. The 9 small `_count_*_since` / `_sum_*_since` helpers are essentially "give me delta from llm_call_ledger after id N" — a single `_ledger_delta(call_kind, before_id) -> {count, cache_hits, cost_usd}` would replace 6 of them.

**Recommended refactor**: extract each phase into a `_run_phase_<name>()` function returning a small `PhaseResult` dataclass; `run_pipeline()` becomes a thin sequencer + `pipeline_runs` writer. This is mechanical (no behavior change), buys ~600 lines, and unblocks M3 from compounding into 2000+. **MEDIUM priority — bundle into M3-M0 (an M3 housekeeping task) per the user-observable-deliverable rule: pair the refactor with one M3 user-visible feature so it doesn't violate the "no pure infra milestones" rule.**

**Web routes complexity**: `routes.py` at 576 lines is fine — 9 endpoints + 5 helpers, each doing one thing. `_compute_all_tab_counts` (added M2-013) is correctly internal. **No action.**

---

## Prioritized refactor recommendations

| Priority | Refactor | Effort | Why now |
|---|---|---|---|
| **HIGH** | **Fix C18 → postings propagation gap.** Add `_write_postings_extracted()` to write `canonical_company / canonical_seniority / canonical_title / canonical_location / team_or_department / top_skills / role_summary / extraction_status='success'` back to `postings` after a successful LLM extraction. Switch `dedup/engine.py:560` and `dedup/merge.py:60` from `seniority_band AS canonical_seniority` to `canonical_seniority`. Drop `seniority_band` after one quality run confirms parity. | **Small** (2–3 hours) | M3 will run new calibration against LLM-extracted ground truth. Today's calibration silently uses a stale-or-NULL seniority field; M3 calibration will look broken when it isn't. Same root cause as the BACKLOG line-198 propagation gap — fix once. |
| **HIGH** | **Consolidate 6 TDD "M2 update" footnotes into entry bodies.** Especially §C9 where 4 stacked notes contradict each other. | **Small** (1 hour) | M3 planning reads TDD §C18 / §C21 / §C29 closely — clean entries reduce subagent confusion. |
| **MED** | **Decompose `pipeline.py` into per-phase functions.** Extract `_run_extraction_phase()`, `_run_embedding_phase()`, `_run_dedup_phase()`. Replace the 9 `_count_*_since` / `_sum_*_since` helpers with a single `_ledger_delta(call_kind, before_id)`. Bundle with one user-visible M3 feature (e.g., the M3 fit_score chip on cards) to honor the "no pure infra milestone" rule. | **Medium** (~1 day) | File is 1480 lines and crosses our 500-line discipline threshold. M3 adds at least 3 more pipeline phases (fit-score classification, hard filter, soft rank). Without this refactor M3 lands in a 2000+ line file. |
| **MED** | **Drop `dedup.auto_merge_threshold`** from `config/dedup.yaml` and `DedupConfig`. Document the 3-tier logic only. | **Small** (15 min) | Leftover field reads into a dataclass; misleads next reader. Live behaviour is gatekeeper-only. |
| **MED** | **Add `unapply` endpoint to TDD §C8** endpoint table; collapse C9 4-footnote stack. | **Small** (30 min) | Doc accuracy. |
| **LOW** | **Standardise config loaders** on the `llm/providers/config.py` Pydantic + lru_cache pattern (3 different loaders today). | **Small per file** | Cosmetic; no bug today. |
| **LOW** | **Move `saved-searches.yaml`** into `docs/poc/SETUP.md` or rename it to make clear it is not a runtime config. | **Small** (15 min) | Avoids future confusion about which YAMLs the code actually reads. |
| **LOW** | **Mark TDD §1.2a `postings.embedding` schema-delta note as resolved**; sync §1.6 Configuration list with actual per-component YAML files. | **Small** (15 min) | Doc cleanup. |
| **LOW** | **Consolidate `init_db.py` `_ensure_*` helpers** into a single migrations table once a 5th column lands. | **Small** | Premature today; flag for M3. |

---

## Recommended action for M3 planning

**Bundle into M3 (do these now — they will be cheaper than after M3 lands new components)**:

1. **HIGH — C18 → postings propagation fix.** Add this as `TASK-M3-001` (or whatever the first M3 task ends up being). It is a prerequisite for any M3 calibration work on classification accuracy.
2. **HIGH — TDD footnote consolidation pass.** Do this *before* drafting M3 task specs so subagents read clean entries. Owned by architect; should happen in `/milestone-plan` Step 2.
3. **MED — `pipeline.py` decomposition.** Bundle with the first M3 task that adds a new pipeline phase (likely fit-score / hard filter). The decomposition unblocks the new phase from compounding.
4. **MED — Drop legacy `auto_merge_threshold` field** + add `unapply` to §C8 + collapse §C9 footnotes — bundle as a single small "doc + config cleanup" task at the start of M3.

**Defer to MVP-M1**:

- Standardise config loaders, move `saved-searches.yaml`, consolidate migrations — none of these block correctness. MVP-M1 is the right time when reliability + UX hardening is the focus.
- Schema cleanup of unused `postings.salary_min_cad / industry / fit_score / tags / …` — these become live at M3, so leaving them is correct.
- `applied.status` CHECK constraint update for `Inactive` / `Expired` — load-bearing only at MVP-M1.

**Skip**:

- Standalone refactor milestone. The user's explicit rule against pure infra milestones applies — every infra recommendation above must ride alongside a user-visible feature.
- Renaming / restructuring of the `dedup/` package. The four files (engine, merge, repost, classifier, calibrate, url_dedup) cleanly separate decision/write/calibration/url-side and the boundaries are correct.
