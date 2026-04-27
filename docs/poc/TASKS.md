# Tasks — jd-matcher — PoC

> **Phase**: PoC
> **Last Updated**: 2026-04-27

---

## Progress Summary

**Active milestone**: M2 — Content-aware dedup + repost detection (+ title pre-filter) — opened 2026-04-27.

| Metric | Active milestone | Project total |
|--------|------------------|---------------|
| Done | 1 | 15 |
| In Progress | 0 | 0 |
| To Do | 12 | 12 |
| Blocked | 0 | 0 |
| Completed milestones | — | 1 (M1) |
| Invalidated tasks | — | 0 |

---

## Active Milestone

### Milestone 2 — Content-aware dedup + repost detection (+ title pre-filter)

**Goal**: Recognize same job posted twice (cross-source or repost); merge into one card. Cheap title-deny-list pre-filter saves ~30-50% of LLM tokens by dropping obviously-irrelevant postings before LLM extraction.

**User-observable deliverable**:
- Browser: merged cards with "Sources: [Apply on LinkedIn] [Apply on Indeed]"; dismissing one variant suppresses canonical across all sources; reposted JDs (30+ days) show "Reposted" badge with original first_seen preserved.
- Backend: title-deny-list filter saves ~30-50% of LLM tokens; filter accuracy validated against ≥95% precision + ≥98% recall.

**Quality bars** (per ROADMAP §M2 + M2 design):
- ≥90% accuracy on 30 hand-labeled posting pairs (10 dup / 10 non-dup / 10 ambiguous)
- ZERO false-merges on 10 different-team cases (regression-blocking)
- Cross-source merge verified on ≥3 real cross-source pairs
- State inheritance: dismissing one source variant suppresses canonical across all sources
- Repost detection on ≥3 real cases or synthetic (30-day threshold)
- Auto-merge threshold 0.90 calibrated against hand-labeled set
- Title filter: ≥95% precision + ≥98% recall (NOT regression-blocking; user-tunable)

**Components introduced or significantly changed**:
- C18 LLM Extraction (new) — TDD §C18
- C19 Title-Based Interest Filter (new) — TDD §C19
- C20 Embedding Pipeline (new) — TDD §C20
- C21 Two-Stage Dedup Engine (new) — TDD §C21
- C22 State Manager extension — TDD §C22
- C28 LLM Provider Abstraction (new) — TDD §C28
- C29 Canonical Record Merge Logic (new) — TDD §C29
- C30 Repost Detector (new) — TDD §C30
- C2 Data store schema additions — TDD §1.2a (4 new tables + email_ingest_log delta)
- C5 Hydrator (changed) — TDD §C5
- C7 State Manager (changed) — TDD §C7
- C8 Web UI backend (changed) — TDD §C8
- C9 Web UI frontend (changed) — TDD §C9
- C11 Pipeline orchestrator (changed) — TDD §C11

**Backlog promotions**: none for M2 from existing BACKLOG.

---

##### TASK-M2-001 — Schema migration (4 new tables + email_ingest_log delta)

- **Status**: Done (2026-04-27)
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C2 (Data store) — TDD §1.2a schema (4 new tables) + email_ingest_log columns
- **Description**: Add `canonical_postings`, `posting_canonical_links`, `posting_embeddings`, `llm_call_ledger` tables + `filter_status`/`filter_reason` columns on `email_ingest_log`. Foundation for entire M2 work. `init_db` must remain idempotent.
- **Dependencies**: None
- **Implementation Checklist**:
  - Schema: 4 new `CREATE TABLE IF NOT EXISTS` in `schema.sql`; 2 `ALTER TABLE` on `email_ingest_log`; `CREATE INDEX IF NOT EXISTS` for join-heavy queries (`idx_canonical_user_block`, `posting_canonical_links` lookups, etc.)
  - Wire: extend `init_db()` to create new tables/indexes; existing M1 init code unchanged
  - Call site: `init_db()` is called by every CLI entry point; no new call sites
  - Imports affected: `src/jd_matcher/db/init_db.py`
  - Runtime files: existing `~/.jd-matcher/jd-matcher.db` extends in place
- **Demo Artifact**: `sqlite3 ~/.jd-matcher/jd-matcher.db ".schema canonical_postings posting_canonical_links posting_embeddings llm_call_ledger"` shows all 4 new tables + extended `email_ingest_log`.
- **Quality log**: `docs/poc/quality-logs/TASK-M2-001.md`
- **Acceptance Criteria**:
  - [x] All 4 new tables created via `CREATE TABLE IF NOT EXISTS` (idempotent)
  - [x] `email_ingest_log` gains `filter_status TEXT NULL` + `filter_reason TEXT NULL` + `idx_email_ingest_log_filter`
  - [x] All canonical-related indexes created (`idx_canonical_user_block` uses `(user_id, canonical_company, team_or_department, canonical_location)`)
  - [x] `init_db()` re-run on populated DB preserves all data, no errors
  - [x] Test: each new table exists with expected columns + indexes
  - [x] Test: re-running `init_db` on a populated DB doesn't drop or error

---

##### TASK-M2-002 — OpenAI API key setup + .env + SETUP.md

- **Status**: In Progress
- **Blocked reason**:
- **Agent**: data-pipeline (+ content-writer for SETUP.md narrative)
- **Component**: C28 prep (env config foundation) — TDD §C28
- **Description**: Document OpenAI API key acquisition + add `OPENAI_API_KEY` to `.env.example` + SETUP.md. Smoke-test helper validates the key works.
- **Dependencies**: None
- **Implementation Checklist**:
  - Schema: N/A
  - Wire: helper `get_openai_key()` in `src/jd_matcher/llm/__init__.py` reads `OPENAI_API_KEY` env var; raises `ConfigError` with clear message if missing
  - Call site: smoke script `python -m jd_matcher.llm.smoke` calls a 1-token completion to verify
  - Imports affected: new module `src/jd_matcher/llm/__init__.py`
  - Runtime files: `tokens.json` unchanged (this is a separate API)
- **Demo Artifact**: `.env.example` has `OPENAI_API_KEY=sk-...` placeholder; SETUP.md has section "OpenAI API key setup" with `platform.openai.com` walkthrough; `python -m jd_matcher.llm.smoke` returns success.
- **Quality log**: `docs/poc/quality-logs/TASK-M2-002.md`
- **Acceptance Criteria**:
  - [x] `.env.example` contains `OPENAI_API_KEY` entry with placeholder
  - [x] `SETUP.md` has section "OpenAI API key setup" describing how to get a key + where to put it
  - [x] `get_openai_key()` helper reads env var or raises `ConfigError` with clear message
  - [x] Test (mocked): missing env var produces `ConfigError` with actionable message
  - [ ] AC #5: Smoke script `python -m jd_matcher.llm.smoke` works end-to-end against real OpenAI (live test) — pending user manual verification after OPENAI_API_KEY set in .env

---

##### TASK-M2-003 — Title-Based Interest Filter (C19) + config/title_filters.yaml

- **Status**: To Do
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C19 (Title-Based Interest Filter) — TDD §C19
- **Description**: Pre-LLM filter sitting between C4 (URL parser) and C5 (hydrator). Drops obviously-irrelevant titles per deny list. Filter decision logged to `email_ingest_log`; filtered postings never proceed to hydration or LLM. Configurable via `config/title_filters.yaml`.
- **Dependencies**: TASK-M2-001
- **Implementation Checklist**:
  - Schema: writes to `email_ingest_log.filter_status` + `filter_reason`
  - Wire: new module `src/jd_matcher/filter/title_filter.py` exposing `filter_title(title) -> FilterDecision`
  - Config: new file `config/title_filters.yaml` with `deny_patterns[]` + `allow_patterns[]` (defaults provided per TDD §C19 examples)
  - Call site: invoked from `pipeline.py` between C4 and C5; filtered postings short-circuit (no hydration call)
  - Imports affected: `pipeline.py`
  - Runtime files: `config/title_filters.yaml` (committed to repo)
- **Demo Artifact**: `python -m jd_matcher.filter.title_filter --title "Director of Engineering"` returns drop decision with matched pattern; `--title "Senior Data Scientist"` returns pass.
- **Quality log**: `docs/poc/quality-logs/TASK-M2-003.md`
- **Acceptance Criteria**:
  - [ ] `config/title_filters.yaml` with default `deny_patterns` (Director|VP|Head of|Chief, Software Engineer/Developer without DS/ML adjacent, Dashboard Developer, Business Intelligence, QA/DevOps/Frontend/Backend Engineer without Data context) and `allow_patterns` (escape hatch, e.g., "Director.*Data Science")
  - [ ] `filter_title(title)` returns `FilterDecision {action: pass|drop, matched_pattern, reason}`
  - [ ] Filter applied between C4 and C5 in pipeline; filtered postings recorded in `email_ingest_log` with `filter_status='filtered'` and `filter_reason` set
  - [ ] Filtered postings NEVER reach hydration, LLM extraction, embedding, or dedup
  - [ ] 100% on synthetic test fixtures (20 deny-matching titles, 20 allow-matching titles, 10 ambiguous)
  - [ ] No live network calls in test path

---

##### TASK-M2-004 — Filter correctness validation (user reviews filtered list)

- **Status**: To Do
- **Blocked reason**:
- **Agent**: data-pipeline + user
- **Component**: C19 (validation) — TDD §C19
- **Description**: Run C19 against the existing 91 real postings + any new postings during M2 implementation window. Generate a validation report showing all filtered titles + matched patterns. User reviews the list and adjusts `config/title_filters.yaml` until precision ≥95% (filtered = irrelevant) and recall ≥98% (legit jobs not lost).
- **Dependencies**: TASK-M2-003
- **Implementation Checklist**:
  - Schema: reads `email_ingest_log`
  - Wire: new module `src/jd_matcher/filter/validate.py` with `python -m jd_matcher.filter.validate` CLI
  - Call site: standalone CLI; no pipeline integration needed
  - Imports affected: new module
  - Runtime files: writes report to `docs/poc/quality-logs/TASK-M2-004-validation-report.md` (or similar)
- **Demo Artifact**: Validation report at `docs/poc/quality-logs/TASK-M2-004-validation-report.md` showing filtered titles, matched patterns, user-confirmed precision/recall numbers; final tuned `config/title_filters.yaml` committed.
- **Quality log**: `docs/poc/quality-logs/TASK-M2-004.md`
- **Acceptance Criteria**:
  - [ ] Validation script outputs filtered postings table (id, title, matched_pattern) for user review
  - [ ] User reviews ALL filtered titles; flags any false positives (legitimate roles incorrectly filtered)
  - [ ] User adjusts `config/title_filters.yaml` patterns based on flags
  - [ ] Re-run validation script; iterate until precision ≥95% on user-confirmed labels
  - [ ] Re-run validation script; iterate until recall ≥98% (false-negative rate ≤2%)
  - [ ] Final tuned `config/title_filters.yaml` committed
  - [ ] Validation report documenting final precision/recall + user judgment basis

---

##### TASK-M2-005 — LLM Provider Abstraction (C28)

- **Status**: To Do
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C28 (LLM Provider Abstraction) — TDD §C28
- **Description**: Define `LLMExtractor` + `EmbeddingProvider` interfaces with cloud (OpenAI) implementation. Stub Ollama implementation as placeholder for future swap (per ROADMAP §M2 + user direction). Cost pricing table per model.
- **Dependencies**: TASK-M2-001, TASK-M2-002
- **Implementation Checklist**:
  - Schema: writes to `llm_call_ledger`
  - Wire: new module `src/jd_matcher/llm/providers/` with:
    - `base.py`: `LLMExtractor` + `EmbeddingProvider` Protocol/ABC
    - `openai_extractor.py`: cloud impl using `openai` library
    - `openai_embedding.py`: cloud impl using `openai` library
    - `ollama_extractor.py`: stub raising `NotImplementedError` (placeholder)
    - `factory.py`: `from_config(provider_name)` routing
  - Config: extend `config.yaml` with `extraction_provider: openai` (default) and `embedding_provider: openai` (default)
  - Call site: C18 + C20 use the abstraction; never import `openai` directly
  - Imports affected: new module under `src/jd_matcher/llm/`
  - Runtime files: writes to `llm_call_ledger`
- **Demo Artifact**: `python -c "from jd_matcher.llm import LLMExtractor; e = LLMExtractor.from_config(); print(type(e).__name__)"` returns `OpenAIExtractor`.
- **Quality log**: `docs/poc/quality-logs/TASK-M2-005.md`
- **Acceptance Criteria**:
  - [ ] `LLMExtractor` + `EmbeddingProvider` Protocols defined with `extract()` and `embed()` methods
  - [ ] `OpenAIExtractor` implementation using GPT-4o-mini (model name configurable)
  - [ ] `OpenAIEmbedding` implementation using `text-embedding-3-small`
  - [ ] Ollama stubs raise `NotImplementedError` with clear message about M3 benchmark sub-task
  - [ ] Factory pattern: `from_config(provider_name)` returns correct implementation
  - [ ] Pricing table in `providers/pricing.py` with `model` + `input_cost_per_1k` + `output_cost_per_1k` + `as_of_date`
  - [ ] `llm_call_ledger` row written per call (provider, model, input_tokens, output_tokens, cost_usd, latency_ms)
  - [ ] Tests mock at the openai client boundary (no live calls)

---

##### TASK-M2-006 — LLM Extraction (C18) — strict canonical labels

- **Status**: To Do
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C18 (LLM Extraction) — TDD §C18
- **Description**: Per-posting extraction via GPT-4o-mini (through C28 abstraction). Strict canonical labels enforced via Pydantic enums (`canonical_seniority`, `canonical_location`). Caches by `full_jd` hash.
- **Dependencies**: TASK-M2-001, TASK-M2-005
- **Implementation Checklist**:
  - Schema: reads/writes `posting_embeddings` cache index; writes `llm_call_ledger` via C28
  - Wire: new module `src/jd_matcher/llm/extract.py` exposing `extract_canonical(posting) -> CanonicalExtraction`
  - Pydantic models: `CanonicalExtraction` with strict enum fields per TDD §C18
  - Prompt template: defined as constant in `extract.py` per TDD §C18 prompt sketch
  - Call site: `pipeline.py` (between hydration and embedding)
  - Cache: by `SHA256(full_jd)` — re-using stored extractions on identical content
  - Imports affected: new module + small change to `pipeline.py`
  - Runtime files: extends `~/.jd-matcher/jd-matcher.db` (`canonical_postings`, `posting_canonical_links` via downstream tasks)
- **Demo Artifact**: `python -m jd_matcher.llm.extract --posting-id 91` outputs `CanonicalExtraction` JSON for that real posting.
- **Quality log**: `docs/poc/quality-logs/TASK-M2-006.md`
- **Acceptance Criteria**:
  - [ ] `extract_canonical(posting)` takes `full_jd` + optional priors; returns `CanonicalExtraction` Pydantic model
  - [ ] `CanonicalExtraction` enforces strict enums for seniority + location (Pydantic validation; out-of-enum = parse failure → retry with stricter prompt)
  - [ ] `canonical_company` normalized (no Inc/Ltd suffixes — verified by 5 test cases)
  - [ ] `team_or_department` canonical (2-5 words, org-unit only — not role-level)
  - [ ] Cache by `SHA256(full_jd)` hit on second `extract_canonical` call (verified by mock count)
  - [ ] `llm_call_ledger` row written per call with cost
  - [ ] Retry on transient OpenAI errors (3 attempts with exponential backoff)
  - [ ] 10 hand-crafted synthetic test JDs all extract within enum constraints (deterministic part)
  - [ ] Live test (one real posting): all canonical fields populated and valid against enum

---

##### TASK-M2-007 — Embedding Pipeline (C20)

- **Status**: To Do
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C20 (Embedding Pipeline) — TDD §C20
- **Description**: Embed `role_summary` via `text-embedding-3-small`. Store as BLOB in `posting_embeddings`. Cache by text hash.
- **Dependencies**: TASK-M2-001, TASK-M2-005, TASK-M2-006
- **Implementation Checklist**:
  - Schema: writes `posting_embeddings`; writes `llm_call_ledger`
  - Wire: new module `src/jd_matcher/llm/embed.py` exposing `embed_posting(posting_id) -> Embedding`
  - Cache: by `SHA256(role_summary)`
  - Storage: 1536-dim float vector packed as `struct.pack` into BLOB (or `numpy.tobytes`)
  - Call site: `pipeline.py` (after C18 extraction)
  - Imports affected: new module + small change to `pipeline.py`
  - Runtime files: `posting_embeddings` table
- **Demo Artifact**: `python -m jd_matcher.llm.embed --posting-id 91` embeds `role_summary`; `sqlite3 ... "SELECT length(embedding), model_name FROM posting_embeddings WHERE posting_id=91"` shows ~6KB blob (1536 × 4 bytes).
- **Quality log**: `docs/poc/quality-logs/TASK-M2-007.md`
- **Acceptance Criteria**:
  - [ ] `embed_posting(posting_id)` takes posting; calls `EmbeddingProvider.embed(role_summary)`; stores in `posting_embeddings`
  - [ ] Vector dimension is 1536 (`text-embedding-3-small` spec)
  - [ ] Cache by `SHA256(text)` hit on second `embed_posting` call (verified)
  - [ ] `llm_call_ledger` row written per call
  - [ ] Cosine sanity check: 5 synthetic dup pairs all have cosine ≥0.85 between their embeddings
  - [ ] Anti-test: 5 different-role pairs have cosine ≤0.7
  - [ ] Live test (one real posting): vector dim 1536 + non-zero
  - [ ] Helper `cosine(v1, v2) -> float` exposed for downstream use

---

##### TASK-M2-008 — Two-Stage Dedup Engine (C21) — BLOCK + FUSE

- **Status**: To Do
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C21 (Two-Stage Dedup Engine) — TDD §C21
- **Description**: BLOCK by `(canonical_company, team_or_department, canonical_location)`; FUSE `0.4×emb + 0.3×skills + 0.2×title + 0.1×seniority`; auto-merge at 0.90. Returns `DedupDecision`.
- **Dependencies**: TASK-M2-001, TASK-M2-006, TASK-M2-007
- **Implementation Checklist**:
  - Schema: reads `canonical_postings` (Stage 1 BLOCK), reads `posting_embeddings` (Stage 2 FUSE)
  - Wire: new module `src/jd_matcher/dedup/engine.py` exposing `decide(posting) -> DedupDecision`
  - Helpers: `cosine(v1, v2)`, `jaccard(s1, s2)`, `title_cosine(t1, t2)` (use sklearn or simple impl)
  - Call site: `pipeline.py` (after C20 embedding)
  - Imports affected: new module
  - Runtime files: none (read-only at this stage; writes happen in C29)
- **Demo Artifact**: `python -m jd_matcher.dedup decide --posting-id 91` outputs `DedupDecision` JSON.
- **Quality log**: `docs/poc/quality-logs/TASK-M2-008.md`
- **Acceptance Criteria**:
  - [ ] `decide(posting)` returns `DedupDecision {action: 'merge'|'new', target_canonical_id, similarity, merge_kind, telemetry}`
  - [ ] BLOCK: SQL uses `idx_canonical_user_block` (verified by `EXPLAIN QUERY PLAN` — no full table scan)
  - [ ] FUSE formula: `0.4×emb_cosine + 0.3×skills_jaccard + 0.2×title_cosine + 0.1×seniority_match` (verified by 5 test cases with known inputs/outputs)
  - [ ] Auto-merge threshold 0.90 (configurable via `config.yaml`)
  - [ ] Inactive/Expired bypass: canonicals in those states are excluded from BLOCK candidates (no-op at M2 since neither status exists yet — placeholder for MVP-M1)
  - [ ] Synthetic test fixtures cover all 4 user scenarios (cross-team / same-team-different-role / cross-source / different-location)
  - [ ] ZERO false-merges on 10 different-team synthetic pairs (regression-blocking)
  - [ ] `DedupDecision` serialization works (Pydantic JSON)

---

##### TASK-M2-009 — Canonical Merge + Repost Detector (C29 + C30)

- **Status**: To Do
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C29 (Canonical Record Merge Logic) + C30 (Repost Detector) — TDD §C29, §C30
- **Description**: When dedup returns merge action, apply merge semantics (preserve postings; INSERT `canonical_postings` + `posting_canonical_links`). Repost detector retags `merge_kind='repost'` if 30+ days from latest prior link; emits `posting_reposted` event.
- **Dependencies**: TASK-M2-001, TASK-M2-008
- **Implementation Checklist**:
  - Schema: writes `canonical_postings`, `posting_canonical_links`; reads `canonical_postings` on merge; writes `events` table for repost
  - Wire: new module `src/jd_matcher/dedup/merge.py` exposing `apply_decision(decision, posting) -> MergeResult`; new module `src/jd_matcher/dedup/repost.py` for the retagger
  - Call site: `pipeline.py` (after C21 `decide`)
  - Imports affected: new modules
  - Runtime files: `canonical_postings` + `posting_canonical_links` extends in place
- **Demo Artifact**: integration test merges 2 synthetic postings; verifies `canonical_postings` has 1 row, `posting_canonical_links` has 2 rows, `postings` still has both originals + `first_seen` MIN preserved.
- **Quality log**: `docs/poc/quality-logs/TASK-M2-009.md`
- **Acceptance Criteria**:
  - [ ] On `action="new"`: INSERT `canonical_postings` + INSERT `posting_canonical_links` (`merge_kind='new'`)
  - [ ] On `action="merge"`: INSERT `posting_canonical_links` (`merge_kind='content_dedup'`); UPDATE `canonical_postings` (MIN `first_seen` preserved, MAX `last_seen`, longer-by-10% `full_jd` swap with provenance)
  - [ ] `postings` table NEVER modified on merge (verified by test that captures `postings.*` before+after)
  - [ ] `sources_summary` correctly appends source values (e.g., `["linkedin_email", "indeed_email"]`)
  - [ ] Transactional — partial failure rolls back (verified by mock of UPDATE failure)
  - [ ] Repost detection: `candidate.first_seen ≥ MAX(prior link merged_at) + 30 days` → retag `merge_kind='repost'` (verified)
  - [ ] On repost: emit `posting_reposted` event via C10 (write to `events` table; verified)
  - [ ] Inactive/Expired bypass: never reaches C30 (already filtered at C21 — verified by mock of canonical with Inactive status)
  - [ ] 8 invariant tests for merge correctness; 5 invariant tests for repost detection

---

##### TASK-M2-010 — Pipeline orchestrator + State Manager extension (C11 + C22)

- **Status**: To Do
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C11 (Pipeline orchestrator) + C22 (State Manager extension) — TDD §C11, §C22
- **Description**: Wire C19→C18→C20→C21→C29→C30 sequence into C11. Add C22 read-side state manager (canonical-id keyed) for state inheritance.
- **Dependencies**: TASK-M2-009, TASK-M2-003
- **Implementation Checklist**:
  - Schema: writes `pipeline_runs` (new sources: `title_filter`, `llm_extraction`, `embedding`); reads `canonical_postings` + `posting_canonical_links`
  - Wire: extend `pipeline.py` orchestrator; new module `src/jd_matcher/state/canonical_view.py` for C22
  - Call site: existing `/sync` endpoint; existing CLI entry
  - Imports affected: `pipeline.py` extends; `state/` adds `canonical_view` module
  - Runtime files: `pipeline-*.jsonl` logs gain new step events
- **Demo Artifact**: `python -m jd_matcher.pipeline` runs full sync; `canonical_postings` + `posting_canonical_links` + `posting_embeddings` + `llm_call_ledger` all populated; `pipeline_runs` shows new sources for filter/llm/embedding phases.
- **Quality log**: `docs/poc/quality-logs/TASK-M2-010.md`
- **Acceptance Criteria**:
  - [ ] Pipeline order: fetch → parse → C19 filter → URL-dedup → hydrate → LLM-extract → embed → content-dedup → merge → store (verified by integration test)
  - [ ] Each new step writes its own `pipeline_runs` row (`title_filter`, `llm_extraction`, `embedding`) with `health_status`; mandatory-persistence invariant from M1-008 holds
  - [ ] C22 `select_main` returns canonical-level cards (not posting-level) — verified by integration test
  - [ ] Apply-one-suppress-all invariant: dismissing one merged variant suppresses canonical from Main on next render — verified by 2-source synthetic test
  - [ ] Persistence across restart: state inheritance works after server restart
  - [ ] Filtered postings (from C19) short-circuit; do NOT appear in any subsequent stage's `pipeline_runs` counts

---

##### TASK-M2-011 — Web UI updates (C8 + C9) — multi-source + Reposted badge

- **Status**: To Do
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C8 (Web UI: backend) + C9 (Web UI: frontend) — TDD §C8, §C9
- **Description**: Backend Main view projects from `canonical_postings`; cards show "Sources: [Apply on LinkedIn] [Apply on Indeed]"; Reposted badge on canonicals with `merge_kind='repost'` in their link history.
- **Dependencies**: TASK-M2-010
- **Implementation Checklist**:
  - Schema: reads `canonical_postings` + `posting_canonical_links`
  - Wire: extend `routes.py` main view query; extend `_card.html` / templates with multi-source rendering + Reposted badge
  - CSS: `.badge-reposted` styling
  - JS: action handlers (apply/dismiss/restore/unapply) target canonical-id (via posting-id-to-canonical-id resolution server-side)
  - Imports affected: `routes.py` + templates
  - Runtime files: existing assets
- **Demo Artifact**: Browser shows merged cards with "Sources: [Apply on LinkedIn] [Apply on Indeed]"; cards with repost link history show "Reposted" badge inline.
- **Quality log**: `docs/poc/quality-logs/TASK-M2-011.md`
- **Acceptance Criteria**:
  - [ ] Cards render `Sources: [Apply on LinkedIn] [Apply on Indeed]` when canonical has multi-source link
  - [ ] Reposted badge renders for canonicals with at least one `merge_kind='repost'` in `posting_canonical_links`
  - [ ] Apply/dismiss/restore/unapply endpoints work on canonical-level state (verified — dismissing a merged card hides ALL variants on next render)
  - [ ] Card-viewed (`e` key) and card-greying (opacity 0.6) work correctly with canonical-id (one card per canonical, not per posting)
  - [ ] DOM tests for new template elements (multi-source list, Reposted badge)
  - [ ] No regression in M1 UI tests (all 443+ existing UI tests still pass)

---

##### TASK-M2-012 — Real-data validation + threshold calibration

- **Status**: To Do
- **Blocked reason**:
- **Agent**: data-pipeline + user
- **Component**: C21 (calibration) + C29 (validation) — TDD §C21, §C29
- **Description**: Generate 30 synthetic test pairs (10 dup / 10 non-dup / 10 ambiguous) covering all 4 scenarios. Run M2 pipeline against existing 91+ postings. User labels 10-15 real pairs. Calibration script computes precision/recall at multiple thresholds; final threshold finalized in config.
- **Dependencies**: TASK-M2-011
- **Implementation Checklist**:
  - Schema: reads `posting_canonical_links` + `canonical_postings`
  - Wire: new module `src/jd_matcher/dedup/calibrate.py` with `python -m jd_matcher.dedup calibrate` CLI
  - User input: labels at `tests/fixtures/dedup_labels.csv` (or similar) — user-editable file
  - Imports affected: new module
  - Runtime files: writes calibration report to `docs/poc/quality-logs/TASK-M2-012-calibration-report.md`
- **Demo Artifact**: Calibration report shows precision/recall at thresholds (0.85/0.88/0.90/0.92/0.95); final threshold committed in `config.yaml`.
- **Quality log**: `docs/poc/quality-logs/TASK-M2-012.md`
- **Acceptance Criteria**:
  - [ ] 30 synthetic test fixtures generated (10 dup / 10 non-dup / 10 ambiguous) covering all 4 scenarios from C21 sample selection
  - [ ] User labels 10-15 real pairs from existing 91+ postings (CSV or YAML)
  - [ ] Calibration script computes precision/recall at thresholds `[0.85, 0.88, 0.90, 0.92, 0.95]`
  - [ ] Precision ≥90% at chosen threshold (regression-checked against synthetic + real labels)
  - [ ] ZERO false-merges on 10 different-team synthetic cases (regression-blocking — must pass at chosen threshold)
  - [ ] Final threshold committed in `config.yaml` (could remain 0.90 or adjust)
  - [ ] Calibration report committed as a quality artifact

---

##### TASK-M2-013 — M2 demo + user approval

- **Status**: To Do
- **Blocked reason**:
- **Agent**: manual (user)
- **Component**: M2 milestone deliverable acceptance — references all M2 C-components
- **Description**: User runs full sync against current Gmail; observes merged cards with multi-source list; verifies state inheritance; confirms Reposted badge for any 30+ day reposts; explicitly approves M2 deliverable.
- **Dependencies**: TASK-M2-012
- **Implementation Checklist**:
  - Schema: N/A
  - Wire: N/A (demo task)
  - Call site: user runs sync via UI
  - Imports affected: N/A
  - Runtime files: N/A
- **Demo Artifact**: User-approved milestone closure (recorded in TASK-M2-013 quality log).
- **Quality log**: `docs/poc/quality-logs/TASK-M2-013.md`
- **Acceptance Criteria**:
  - [ ] User runs full sync; observes ≥1 cross-source merged card on Main with "Sources: [Apply on LinkedIn] [Apply on Indeed]"
  - [ ] User dismisses a merged card; refreshes; canonical stays out of Main on next render (state inheritance)
  - [ ] All 6 ROADMAP §M2 ACs verified by user:
    - ≥90% accuracy on 30 hand-labeled pairs
    - ZERO false-merges on different-team cases (per M2-012)
    - Cross-source merge verified on ≥3 real pairs
    - State inheritance: dismissing one suppresses canonical
    - Repost detection: ≥3 real-or-synthetic cases
    - Auto-merge threshold calibrated and recorded
  - [ ] User explicit approval logged

---

## Completed Milestones Log

### Milestone 1 — Raw pipe + URL dedup + applied/dismissed state

- **Closed**: 2026-04-27
- **Outcome**: APPROVED (user approval explicit during /milestone-complete)
- **Tasks**: 14 Done (TASK-M1-001 through TASK-M1-012, plus M1-005b and M1-005c added during the milestone)
- **Quality summary**:
  - Hydration (deterministic, ≥95% bar): LinkedIn 70/70 = 100%, Indeed 21/21 = 100%, Combined 91/91 = 100% — PASS
  - URL extraction (deterministic, ≥95% bar): LinkedIn 100%, Indeed 97.1% (post-M1-005b pagead-fix) — PASS
  - URL dedup (100% required): re-run produces 0 new postings — PASS
  - State persistence (100% required): all 4 transitions (apply/dismiss/restore/unapply) persist across restart — PASS
  - Unit tests: 443 passed, 19 skipped, 0 failed
- **Major auto-fixes during milestone**: 17 (see TASK-M1-011 quality log for full bug list — most surfaced during 2026-04-27 real-data validation against user's live Gmail)
- **Directional decisions**: 3
  - Inactive state model (supersedes auto-remove) — bundled to MVP-M1
  - Expired state for dead-link postings — bundled to MVP-M1 with Inactive
  - Indeed JSON-LD via Sec-Fetch headers (rejected Playwright path) — empirically validated 5/5
- **Scope additions during M1** (all user-approved during session): un-apply action, new/viewed inbox sort, JSON-LD Indeed extraction, per-email ingest log + report CLI (M1-005c, Override BA accepted), Indeed pagead URL resolution (M1-005b), HTML-to-text strip + click-to-select + paragraph preservation
- **Alignment verdict**: ALIGNED (BA Mode B, see ALIGNMENT-LOG.md 2026-04-27)
- **Quality logs**: docs/poc/quality-logs/TASK-M1-001.md through TASK-M1-012.md

#### M1 Task Entries (full audit trail)

**Goal**: Working local pipeline + browser UI showing today's fresh LinkedIn + Indeed jobs with state tracking.
**Deliverable**: User runs `python -m jd_matcher`, opens `localhost:8765`, triages real postings via keyboard, returns next day to find no reappearance of handled cards.
**Review checkpoint**: User approved deliverable on 2026-04-27.

---

##### TASK-M1-001 — Repo bootstrap + project skeleton

- **Status**: Done (2026-04-24)
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C1 (Repo bootstrap) — TDD §C1
- **Description**: Stand up public GitHub repo for jd-matcher with MIT license, README, project skeleton, and Python tooling. Implements commercial hedge 5 (open-source from day 1).
- **Dependencies**: None
- **Implementation Checklist** (filled by architect before task begins):
  - Schema: N/A
  - Wire: `pyproject.toml` package config; `src/jd_matcher/__init__.py` package entry
  - Call site: N/A — first commit
  - Imports affected: N/A
  - Runtime files: `.env.example` (placeholders for GMAIL_OAUTH_CLIENT_PATH, OPENAI_API_KEY, DB_PATH); `requirements.txt`
- **Demo Artifact**: Public GitHub URL `https://github.com/andrew-yuhochi/jd-matcher` rendering README correctly with "Built with Claude Code" badge.
- **Quality log**: `docs/poc/quality-logs/TASK-M1-001.md`
- **Acceptance Criteria**:
  - [ ] Public GitHub repo at `andrew-yuhochi/jd-matcher` accessible
  - [ ] README contains the line `> Built with [Claude Code](https://claude.ai/code)` directly below top description (per CLAUDE.md GitHub Rule #4)
  - [ ] `LICENSE` file present (MIT)
  - [ ] Repo skeleton: `src/jd_matcher/`, `tests/`, `tests/fixtures/`, `docs/poc/` (already exists), `requirements.txt`, `pyproject.toml`, `.gitignore` (excludes `.env`, `*.db`, `__pycache__`, `.venv/`), `.env.example`
  - [ ] `pip install -e .` succeeds cleanly in a fresh virtualenv
  - [ ] `pytest --collect-only` runs without error (no actual tests yet — just config sanity)
  - [ ] First commit pushed to `origin main` (per CLAUDE.md GitHub Rule #3)

---

##### TASK-M1-002 — SETUP.md + saved-search keyword discussion

- **Status**: Done (2026-04-24)
- **Blocked reason**:
- **Agent**: content-writer (with user collaboration)
- **Component**: C12 (Setup task) — TDD §C12
- **Description**: Produce `docs/poc/SETUP.md` — a step-by-step manual setup checklist for the user, including final list of LinkedIn (≥7) and Indeed (≥2) saved-search keywords. content-writer drafts; user reviews + finalizes keyword list interactively. Outcome unblocks user-side alert setup so emails accumulate while later tasks build.
- **Dependencies**: TASK-M1-001
- **Implementation Checklist** (filled by architect before task begins):
  - Schema: N/A
  - Wire: N/A
  - Call site: N/A
  - Imports affected: N/A
  - Runtime files: `docs/poc/SETUP.md` (new); `config/saved-searches.yaml` (new — captures the final keyword lists in machine-readable form for later reference)
- **Demo Artifact**: `docs/poc/SETUP.md` with all 10 manual setup steps; `config/saved-searches.yaml` with final keyword lists. User has set up alerts on at least LinkedIn + Indeed.
- **Quality log**: `docs/poc/quality-logs/TASK-M1-002.md`
- **Acceptance Criteria**:
  - [ ] `docs/poc/SETUP.md` exists with 10 numbered steps covering: dedicated Gmail confirmation, GCP project + Gmail API enabled, OAuth client (Desktop type) downloaded, OpenAI API key configured in `.env`, LinkedIn saved searches set up (per agreed list), Indeed saved searches set up, Job Bank Canada alerts (deferred to M4 — note this), 5 CV variants placed in local folder (deferred wiring to M4 — note this), `python -m jd_matcher.auth` first-run authorization, sanity-check pipeline run
  - [ ] `config/saved-searches.yaml` captures the final user-approved LinkedIn keyword list (≥7 entries) + Indeed keyword list (≥2 entries) with location filters per platform
  - [ ] User has confirmed they have set up the alerts on LinkedIn + Indeed (subjective — user signs off on followability)
  - [ ] SETUP.md cross-references DATA-SOURCES.md sections for each step

---

##### TASK-M1-003 — Data model + idempotent init_db

- **Status**: Done (2026-04-24)
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C2 (Data model / SQLite schema) — TDD §C2
- **Description**: Create SQLite schema for all M1 tables and an idempotent `init_db()` function that creates the database at `~/.jd-matcher/jd-matcher.db` on first run. Every table includes `user_id` column with default `'default'` (commercial hedge 3 — namespace-aware data model).
- **Dependencies**: TASK-M1-001
- **Implementation Checklist**:
  - Schema: `users`, `postings`, `posting_sources`, `seen_urls`, `applied`, `dismissed`, `events`, `pipeline_runs` — all with `user_id` column (default `'default'`); `postings.hydration_status` (`complete`/`partial`/`failed`); `pipeline_runs.health_status` (`healthy`/`degraded`/`failed`) + `failure_reason` + `last_successful_fetch_at`
  - Wire: `src/jd_matcher/db/schema.sql` (raw SQL); `src/jd_matcher/db/init_db.py` exposing `init_db(db_path: Path) -> None`
  - Call site: `src/jd_matcher/__main__.py` (run `init_db()` if DB missing); `tests/conftest.py` (test DB fixture)
  - Imports affected: N/A — new module
  - Runtime files: schema.sql (new); DB at `~/.jd-matcher/jd-matcher.db` (created at runtime)
- **Demo Artifact**: `sqlite3 ~/.jd-matcher/jd-matcher.db ".tables"` shows all 8 tables; running `init_db()` twice produces no errors.
- **Quality log**: `docs/poc/quality-logs/TASK-M1-003.md`
- **Acceptance Criteria**:
  - [x] All 8 tables created with documented columns + types
  - [x] Every table (except `users`, which is the identity anchor with `id` as PK) has `user_id TEXT NOT NULL DEFAULT 'default'` column
  - [x] `postings.hydration_status` column with `CHECK` constraint on (`complete`, `partial`, `failed`)
  - [x] `pipeline_runs.health_status` column with `CHECK` constraint on (`healthy`, `degraded`, `failed`)
  - [x] `init_db()` is idempotent — re-running on existing DB does not error and does not modify data
  - [x] UNIQUE constraints on `seen_urls(user_id, url)` (composite for multi-user namespacing), `(applied.posting_id, applied.user_id)`, `(dismissed.posting_id, dismissed.user_id)`
  - [x] Indexes on `postings.first_seen`, `events.timestamp`, `pipeline_runs.run_id` for query performance
  - [x] Smoke insert test passes: insert one posting, verify retrievable

---

##### TASK-M1-004 — Gmail ingester (OAuth + fetch)

- **Status**: Done (2026-04-24)
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C3 (Gmail Ingester) — TDD §C3
- **Description**: OAuth loopback flow for Gmail API; per-sender fetcher that retrieves recent emails from LinkedIn (`jobalerts-noreply@linkedin.com`) and Indeed (`alert@indeed.com`) addresses. Per-sender try/except writes failure to `pipeline_runs` (`health_status='failed'`) and never re-raises. Synthetic-fixture-first development: build against `tests/fixtures/gmail/*.eml` files to unblock work before user has live email.
- **Dependencies**: TASK-M1-003
- **Implementation Checklist**:
  - Schema: `pipeline_runs` (writes `health_status`, `failure_reason`, `last_successful_fetch_at`)
  - Wire: `src/jd_matcher/ingest/gmail.py` exposes `GmailIngester.fetch_for_sender(sender_filter, since_date) -> list[RawEmail]`; `src/jd_matcher/auth/gmail_oauth.py` for OAuth loopback
  - Call site: invoked by `pipeline.py` orchestrator (TASK-M1-008)
  - Imports affected: new modules
  - Runtime files: `~/.jd-matcher/credentials.json` (user-supplied, .env.example documents path); `~/.jd-matcher/tokens.json` (created on first auth); `tests/fixtures/gmail/*.eml` (synthetic emails)
- **Demo Artifact**: `python -m jd_matcher.auth` runs OAuth once and stores token; `python -m jd_matcher.ingest gmail --sender linkedin --dry-run` lists fetched messages (or fixture messages with `SKIP_LIVE=1`).
- **Quality log**: `docs/poc/quality-logs/TASK-M1-004.md`
- **Acceptance Criteria**:
  - [x] Loopback OAuth flow completes end-to-end: opens browser, redirects to localhost, exchanges code for tokens, stores tokens at `~/.jd-matcher/tokens.json`
  - [x] Refresh-token reuse on subsequent runs — no browser interaction
  - [x] Per-sender fetch with date filter (`newer_than:2d`) and label filter
  - [x] Per-sender try/except: on failure, writes `pipeline_runs` row with `health_status='failed'`, `failure_reason=<exception details>`; returns empty list; never re-raises
  - [x] On success: writes `pipeline_runs` row with `health_status='healthy'` and updates `last_successful_fetch_at`
  - [x] Synthetic fixture tests: 100% on at least 5 LinkedIn + 5 Indeed `.eml` fixture files
  - [x] `SKIP_LIVE=1` env var bypasses live Gmail and reads from `tests/fixtures/gmail/`
  - [x] Live test with real Gmail account (gated by user availability) ≥95% fetch success on a 7-day window

---

##### TASK-M1-005 — Email URL parsers + URL-based dedup

- **Status**: Done (2026-04-24)
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C4 (Email URL parser) + C6 (URL-based dedup) — TDD §C4, §C6
- **Description**: Per-source parsers (LinkedIn + Indeed) extracting posting URL (primary, regex on plain-text part) plus best-effort title/company/location. Output flows through URL-based dedup that checks `seen_urls` before allowing insert. Atomic dedup ensures re-running produces zero new postings.
- **Dependencies**: TASK-M1-003, TASK-M1-004
- **Implementation Checklist**:
  - Schema: `seen_urls` (INSERT on new URL); `postings` + `posting_sources` (INSERT on new URL); raw email body stored to `posting_sources.raw_body`
  - Wire: `src/jd_matcher/parse/linkedin_email.py`, `src/jd_matcher/parse/indeed_email.py` each exposing `parse(raw_email: bytes) -> list[ParsedPosting]`; `src/jd_matcher/dedup/url_dedup.py` exposing `is_seen(url: str) -> bool`, `mark_seen(url: str, posting_id: int)`
  - Call site: invoked by `pipeline.py` orchestrator (TASK-M1-008) per email returned from Gmail ingester
  - Imports affected: new modules
  - Runtime files: `tests/fixtures/gmail/*.eml` (10 LinkedIn + 10 Indeed); `tests/fixtures/parsed_postings/*.json` (expected outputs)
- **Demo Artifact**: `python -m jd_matcher.parse --fixture linkedin/sample-1.eml` returns ParsedPosting list; running same fixture twice through full pipeline produces 0 new postings on second run.
- **Quality log**: `docs/poc/quality-logs/TASK-M1-005.md`
- **Acceptance Criteria**:
  - [x] LinkedIn parser: 100% URL extraction on 10 synthetic `.eml` fixtures (each fixture contains 1-5 postings)
  - [x] Indeed parser: 100% URL extraction on 10 synthetic `.eml` fixtures
  - [x] URL regex pattern: `linkedin.com/jobs/view/(\d+)` for LinkedIn; equivalent for Indeed; raw_body persisted in `posting_sources.raw_body` for replay
  - [x] Best-effort title/company/location extracted when present in email; empty string when not present (no exceptions on missing fields)
  - [x] `seen_urls` atomic insert (transactional) prevents duplicate inserts under concurrent calls
  - [x] Re-run of pipeline against same fixture set produces 0 new postings (URL dedup verified)
  - [x] URL-only fallback: if title/company/location all extraction fails for a posting, the posting is still inserted (URL is the canonical identifier)

---

##### TASK-M1-006 — JD hydrator (LinkedIn + Indeed guest endpoints)

- **Status**: Done (2026-04-24)
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C5 (JD Hydrator) — TDD §C5
- **Description**: Per-URL HTML fetcher for LinkedIn (`linkedin.com/jobs-guest/jobs/api/jobPosting/{jobId}`) and Indeed public pages. Process-wide rate limiter at 1 request per 30 seconds. Per-URL failure inserts posting with `hydration_status='failed'` and best-effort fields — never silently dropped. Source-level health: >20% fail in one run → degraded; 100% → failed (`failure_reason='rate_limit'` or exception text).
- **Dependencies**: TASK-M1-003, TASK-M1-005
- **Implementation Checklist**:
  - Schema: `postings.hydration_status`; `posting_sources.raw_html` (cache); `pipeline_runs` (writes source-level health)
  - Wire: `src/jd_matcher/hydrate/linkedin.py`, `src/jd_matcher/hydrate/indeed.py` each exposing `hydrate(url: str) -> HydratedJD`; `src/jd_matcher/hydrate/rate_limiter.py` (process-wide, threading.Lock-based)
  - Call site: invoked by `pipeline.py` orchestrator (TASK-M1-008) for postings returned from URL dedup as new
  - Imports affected: integrate `py-linkedin-jobs-scraper` parsing utilities (or vendored equivalent) for HTML→JD extraction
  - Runtime files: `tests/fixtures/hydration/*.html` (10 LinkedIn + 10 Indeed); `tests/fixtures/hydrated/*.json` (expected outputs)
- **Demo Artifact**: `python -m jd_matcher.hydrate --url <fixture-url>` returns full JD text from fixture HTML; rate-limit test (`pytest tests/hydrate/test_rate_limiter.py`) measurably enforces 1 req/30 s.
- **Quality log**: `docs/poc/quality-logs/TASK-M1-006.md`
- **Acceptance Criteria**:
  - [x] 100% JD extraction on 10 LinkedIn + 10 Indeed synthetic HTML fixtures
  - [x] Rate limiter measurably enforces 1 request per 30 seconds across the entire process (not per-instance)
  - [x] Per-URL failure path: posting still inserted with `hydration_status='failed'` and `posting_sources.raw_html='ERROR: <reason>'`; logged but not raised
  - [x] Source-level health threshold: >20% per-run fail → next `pipeline_runs` row for that source has `health_status='degraded'`
  - [x] 100% per-run fail → `pipeline_runs.health_status='failed'`, `failure_reason='rate_limit'` if all errors are 429, else exception text
  - [x] Hydrated `raw_html` cached in `posting_sources.raw_html` — never re-fetched for same URL
  - [x] No silent drops verified by integration test: feed 5 URLs (3 success + 2 fail), assert 5 postings end up in `postings` with correct `hydration_status`

---

##### TASK-M1-007 — State manager (applied / dismissed / restore)

- **Status**: Done (2026-04-25)
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C7 (State Manager) — TDD §C7
- **Description**: Logic for posting state transitions: `apply`, `dismiss`, `restore`. Persists to `applied` and `dismissed` tables. Provides main-view query helper that excludes applied + dismissed postings. Auto-removal helper for applied entries unchanged for 3 months exists in M1 but the scheduler is deferred to MVP.
- **Dependencies**: TASK-M1-003
- **Implementation Checklist**:
  - Schema: `applied`, `dismissed` tables (INSERT/DELETE)
  - Wire: `src/jd_matcher/state/manager.py` exposing `mark_applied(posting_id)`, `dismiss(posting_id)`, `restore(posting_id)`, `main_view_postings() -> list[Posting]`, `auto_remove_stale_applied(cutoff_date) -> int`
  - Call site: invoked by web UI endpoints (TASK-M1-009)
  - Imports affected: new module
  - Runtime files: N/A
- **Demo Artifact**: `pytest tests/state/test_state_manager.py` — integration test creates posting, marks applied, restarts in-process DB connection, verifies state preserved across restart and main-view query excludes applied + dismissed.
- **Quality log**: `docs/poc/quality-logs/TASK-M1-007.md`
- **Acceptance Criteria**:
  - [x] `mark_applied(posting_id)` creates a row in `applied` with current timestamp and `status='Applied'` (default)
  - [x] `dismiss(posting_id)` creates a row in `dismissed` with current timestamp; idempotent (re-dismiss is no-op)
  - [x] `restore(posting_id)` deletes from `dismissed`; if not in dismissed, no-op
  - [x] `main_view_postings()` returns postings WHERE `id NOT IN (SELECT posting_id FROM applied) AND id NOT IN (SELECT posting_id FROM dismissed)` — verified against fixture
  - [x] State persists across server restart (integration test closes connection, reopens, reads)
  - [x] `auto_remove_stale_applied(cutoff_date)` exists and is unit-tested — but not auto-triggered in M1 (scheduler is MVP)

---

##### TASK-M1-008 — Pipeline orchestrator + non-hideable health logging

- **Status**: Done (2026-04-25)
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C11 (Pipeline orchestrator) — TDD §C11
- **Description**: Sequence Gmail ingester → email URL parser → URL dedup → JD hydrator → DB store, per source. Per-source isolation: one source failing does NOT cascade to others. Always writes one `pipeline_runs` row per source per run with non-null `health_status`, regardless of outcome. Emits `source_failure` events on health transitions. Structured JSON logs.
- **Dependencies**: TASK-M1-004, TASK-M1-005, TASK-M1-006
- **Implementation Checklist**:
  - Schema: writes `pipeline_runs` (one row per source per run); writes `events` (`source_failure` on transitions)
  - Wire: `src/jd_matcher/pipeline.py` exposing `run_pipeline() -> PipelineRunSummary`; `src/jd_matcher/__main__.py` adds `python -m jd_matcher.pipeline` CLI entry
  - Call site: invoked by `POST /sync` endpoint (TASK-M1-009) and CLI
  - Imports affected: new module
  - Runtime files: `logs/pipeline-*.jsonl` (structured JSON logs)
- **Demo Artifact**: `python -m jd_matcher.pipeline` runs end-to-end on synthetic mailbox; `sqlite3 ... "SELECT source, health_status FROM pipeline_runs"` shows 4 rows (gmail_linkedin, gmail_indeed, hydrator_linkedin, hydrator_indeed); JSON log file shows step-by-step events.
- **Quality log**: `docs/poc/quality-logs/TASK-M1-008.md`
- **Acceptance Criteria**:
  - [x] One `pipeline_runs` row per source per run, with non-null `health_status` — verified by integration test that runs pipeline 3 times and asserts 12 rows total
  - [x] Per-source isolation: integration test forces failure in `hydrator_linkedin` (mock raises) → `gmail_linkedin`, `gmail_indeed`, `hydrator_indeed` still complete with `health_status='healthy'`
  - [x] Health transition emits `source_failure` event in `events` table — fields: `source`, `previous_status`, `new_status`, `failure_reason`, `timestamp`
  - [x] Structured JSON log written to `logs/pipeline-<run_id>.jsonl` — one line per pipeline step
  - [x] End-to-end fixture run: feeding 5 LinkedIn + 5 Indeed fixture emails produces N postings in `postings` table where N matches expected unique URL count
  - [x] Idempotency: re-running on same fixture mailbox produces 0 new postings (URL dedup respected)

---

##### TASK-M1-009 — Web UI backend (FastAPI + 8 endpoints + source-health)

- **Status**: Done (2026-04-25)
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C8 (Web UI: backend) — TDD §C8
- **Description**: FastAPI app serving the three-tab UI plus pipeline-trigger and state-mutation endpoints. Server-rendered Jinja2 HTML + small fragment endpoints for HTMX swaps. Bind to `127.0.0.1` only. Exposes `/api/source-health` for the sub-bar badges. Main view query NEVER filters by `hydration_status`.
- **Dependencies**: TASK-M1-007, TASK-M1-008
- **Implementation Checklist**:
  - Schema: reads `postings`, `applied`, `dismissed`, `pipeline_runs`; writes via state manager (TASK-M1-007)
  - Wire: `src/jd_matcher/web/app.py` (FastAPI app); `src/jd_matcher/web/routes.py` (endpoints); `src/jd_matcher/web/templates/` (Jinja2)
  - Call site: launched via `python -m jd_matcher.web` or `uvicorn jd_matcher.web:app`
  - Imports affected: new module
  - Runtime files: Jinja2 templates (`base.html`, `main.html`, `applied.html`, `dismissed.html`, partials for cards); `static/js/keyboard.js`, `static/css/styles.css`
- **Demo Artifact**: `uvicorn jd_matcher.web:app --host 127.0.0.1 --port 8765` then `curl localhost:8765/healthz` returns 200; opening `http://localhost:8765/` in browser renders Main tab with seeded fixture postings.
- **Quality log**: `docs/poc/quality-logs/TASK-M1-009.md`
- **Acceptance Criteria**:
  - [x] All 9 endpoints respond per contract: `GET /` (Main HTML), `GET /applied` (Applied HTML), `GET /dismissed` (Dismissed HTML), `POST /sync`, `POST /postings/{id}/dismiss`, `POST /postings/{id}/apply`, `POST /postings/{id}/restore`, `GET /healthz`, `GET /api/source-health` (JSON)
  - [x] `GET /api/source-health` returns latest per-source state from `pipeline_runs` — schema: `[{source, health_status, last_run, last_successful_fetch_at, failure_reason}, ...]`
  - [x] Main view query does NOT filter by `hydration_status` — postings with `partial`/`failed` hydration appear (verified by test that seeds 3 hydration-failed postings + asserts they appear in Main HTML response)
  - [x] Bind address is exclusively `127.0.0.1` — `0.0.0.0` rejected (configurable but defaulted to 127.0.0.1; integration test verifies)
  - [x] State-mutation endpoints (`/apply`, `/dismiss`, `/restore`) are idempotent — calling twice produces same DB state
  - [x] All endpoints have integration tests with seeded fixture DB; 100% pass

---

##### TASK-M1-005b — Indeed pagead URL resolution

- **Status**: Done (2026-04-26)
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C4 (URL parser, Indeed sub-flow) — TDD §C4 responsibility (3) + §1.4 dual-rate-limit note
- **Description**: Add HTTP redirect resolution for Indeed `pagead/clk/dl` URLs. Email URL extraction in M1-005 only catches `rc/clk?jk=` URLs (~21% of Indeed jobs); the remaining ~79% are `pagead/clk/dl` redirects with no `jk=` param visible. This task adds a stealth-headers redirect-follow step that resolves `pagead` URLs to their canonical `viewjob?jk=` form for hydration. Validated 8/8 in empirical spike.
- **Dependencies**: TASK-M1-005 (Done), TASK-M1-006 (Done — provides the canonical hydrator path)
- **Implementation Checklist**:
  - Schema: N/A — no DB changes (resolution is a pure parsing-time HTTP step)
  - Wire: new helper module `src/jd_matcher/parse/indeed_pagead.py` exposing `resolve_pagead_urls(urls: list[str]) -> dict[str, str]` (returns `{original_url: canonical_url}` mapping; non-pagead URLs pass through unchanged — idempotent)
  - Call site: `src/jd_matcher/parse/indeed_email.py` — extend the existing Indeed parser to call `resolve_pagead_urls` for matched `pagead/clk` URLs and substitute resolved canonical URLs into the `ParsedPosting` output. The regex extraction in (2) of TDD §C4 is unchanged; pagead resolution is a post-extraction substitution pass.
  - Stealth stack (mandatory — all 8 items per TDD §C4 update; partial implementation will silently fail):
    1. `requests.Session()` reused across all URLs in one email batch (cookies accumulate)
    2. Browser-style static User-Agent (Chrome on macOS)
    3. `Referer: https://mail.google.com/`
    4. Standard browser `Accept` / `Accept-Language` / `Accept-Encoding` headers
    5. `html.unescape()` applied to URL BEFORE the HTTP request — most-likely silent-failure mode; explicit unit test required
    6. `time.sleep(3 + random.uniform(0, 1.5))` jitter between consecutive requests (3.0–4.5s range)
    7. `allow_redirects=True`, `timeout=30`
    8. Discard tracking params (`tk`, `q`, `l`, `from`, …) — keep only `jk=<hex>`
  - Config: support `JD_MATCHER_OFFLINE_PARSE=1` env var to skip resolution entirely (offline-testing opt-out — preserves the earlier no-network-at-parse-time assumption for replay)
  - Imports affected: new module `parse/indeed_pagead.py`; modified `parse/indeed_email.py` (single new import + call)
  - Runtime files: N/A (no logs of its own — flows through the existing pipeline JSON log via the orchestrator)
- **Demo Artifact**: `python -m jd_matcher.parse.indeed_pagead --eml tests/fixtures/real/<indeed-email>.eml` outputs original→canonical URL mapping; integration test runs full pipeline against the 6 real Indeed `.eml` fixtures and shows ≥95% extraction rate (vs ~21% baseline).
- **Quality log**: `docs/poc/quality-logs/TASK-M1-005b.md`
- **Acceptance Criteria**:
  - [x] `resolve_pagead_urls(urls)` returns `{original: canonical}` mapping; URLs without `pagead/clk` substring pass through unchanged (idempotent)
  - [x] `html.unescape()` is called on every URL before the HTTP request — verified by unit test using a URL with `&amp;` entities
  - [x] Sequential requests separated by 3–4.5s jitter — verified by test asserting wall-clock time ≥ N × 3.0s for N requests
  - [x] Browser-mimicking headers applied: `User-Agent` (Chrome-style), `Referer: https://mail.google.com/`, browser-style `Accept` / `Accept-Language` / `Accept-Encoding`
  - [x] `requests.Session()` reused across the URL batch — verified by test asserting session cookies accumulate across consecutive resolutions
  - [x] Tracking params (`tk=`, `q=`, `l=`, `from=`) stripped from the canonical URL — only `jk=<hex>` preserved
  - [x] `JD_MATCHER_OFFLINE_PARSE=1` env var skips all resolution; URLs pass through unmodified (verified by test setting the env var)
  - [x] Integration test against the 6 real Indeed `.eml` fixtures (in `tests/fixtures/real/`) shows ≥95% extraction rate — first-run result: 34/35 (97.1%)
  - [x] Total wall-clock for resolving 5–12 URLs in one email batch is under 75 seconds (≤15 URLs × 5s avg)

---

##### TASK-M1-005c — Per-email ingest log + report

- **Status**: Done (2026-04-26)
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C3 / C4 / C5 (writer hooks) + new C27 (Ingest Report CLI) — TDD §C3, §C4, §C5, §C27, §1.2a (`email_ingest_log` schema)
- **Description**: Add per-email ingestion telemetry so the user can manually cross-check Gmail vs the pipeline's ingestion outcome. Schema-level: new `email_ingest_log` table with one row per ingested email. Writer hooks: C3 inserts the row at fetch; C4 updates URL counts; C5 updates hydration counts. Reporting: new CLI `python -m jd_matcher.report ingest` that queries the table and renders a markdown table for manual inspection. Driven by the M1-005b Indeed `pagead` discovery — generalizable telemetry to catch similar parser failures earlier across any source.
- **Dependencies**: TASK-M1-003 (Done — schema infrastructure), TASK-M1-008 (Done — orchestrator's canonical `pipeline_run_id` source)
- **Implementation Checklist**:
  - Schema: add `email_ingest_log` table per TDD §1.2a (new DDL); `init_db()` must remain idempotent (re-run on existing DB does NOT recreate or fail) — additive `CREATE TABLE IF NOT EXISTS` + indexes
  - Wire — C3 (`src/jd_matcher/ingest/gmail.py`): insert one `email_ingest_log` row per fetched email at fetch time, populating `gmail_message_id`, `source`, `sender`, `subject`, `received_at`, `ingested_at`, `pipeline_run_id`; counters default to 0
  - Wire — C4 (`src/jd_matcher/parse/`): after parsing each email, locate the row by `gmail_message_id` and increment `urls_extracted_count` (regex + pagead-resolved set) and `urls_new_count` (post URL-dedup, from C6)
  - Wire — C5 (`src/jd_matcher/hydrate/`): for each hydration outcome, increment `postings_hydrated_count` (success) or `postings_hydration_failed_count` (failure) on the row whose `gmail_message_id` matches the originating email — requires the orchestrator to thread `gmail_message_id` through to the hydrator alongside each URL
  - Wire — orchestrator (`src/jd_matcher/pipeline.py`): pass canonical `run_id` to C3/C4/C5 so all writers use the same `pipeline_run_id` (NOT a per-source `_ingest_<sender>` sub-run-id — same B1 discriminator pattern as `/api/source-health`)
  - New module: `src/jd_matcher/report.py` exposing the CLI subcommand `ingest` (`python -m jd_matcher.report ingest [--since YYYY-MM-DD] [--source X] [--format markdown|csv]`)
  - Call site: `python -m jd_matcher.report` — new entry point; document in README usage section
  - Imports affected: new module; minor additions to `ingest/gmail.py`, `parse/indeed_email.py` + `parse/linkedin_email.py`, `hydrate/linkedin.py` + `hydrate/indeed.py`, `pipeline.py`
  - Runtime files: N/A (writes to existing SQLite DB only)
- **Demo Artifact**: `python -m jd_matcher.report ingest --since 2026-04-25` outputs a markdown table to stdout with one row per email ingested in the date range (Date · Source · Subject · URLs · New · Posts · Hydrated · Failed) plus aggregate totals row. User opens Gmail and visually compares.
- **Quality log**: `docs/poc/quality-logs/TASK-M1-005c.md`
- **Acceptance Criteria**:
  - [x] `email_ingest_log` table created via idempotent `init_db()` (re-running init_db on existing DB does NOT recreate or fail)
  - [x] C3 inserts one row per fetched email with `gmail_message_id`, `source`, `sender`, `subject`, `received_at`, `ingested_at`, `pipeline_run_id` populated; counters default to 0
  - [x] C4 updates `urls_extracted_count` and `urls_new_count` for the matching `gmail_message_id` row
  - [x] C5 updates `postings_hydrated_count` / `postings_hydration_failed_count` for the matching `gmail_message_id` row (per-posting accumulator across the batch)
  - [x] All writers use the canonical orchestrator `pipeline_run_id` (NOT `_ingest_<sender>` sub-run-id) — verified by integration test querying `SELECT DISTINCT pipeline_run_id FROM email_ingest_log` and asserting 1 row per orchestrator invocation
  - [x] `python -m jd_matcher.report ingest` (no args) renders a markdown table to stdout with all log rows
  - [x] `--since YYYY-MM-DD` filters to rows with `received_at >= date`
  - [x] `--source X` filters to rows where `source = X`
  - [x] `--format csv` outputs valid CSV (parseable by `csv.DictReader`) instead of markdown
  - [x] Bottom of report shows aggregate totals (total emails, total URLs, total new, total posts, total hydrated, total failed) matching column sums
  - [x] Integration test: run full pipeline against fixture mailbox of 5 emails, then assert `email_ingest_log` has exactly 5 rows with non-zero counters

---

##### TASK-M1-010 — Web UI frontend + events instrumentation

- **Status**: Done (2026-04-26)
- **Blocked reason**:
- **Agent**: data-pipeline
- **Component**: C9 (Web UI: frontend) + C10 (Events instrumentation) — TDD §C9, §C10
- **Description**: Vanilla HTML/JS + HTMX frontend. Three tabs (Main / Applied / Dismissed); card list; keyboard shortcuts (`j/k/e/d/a/o/1/2/3/?/Esc`); 180ms slide-left animation on dismiss; sub-bar with non-dismissible per-source health badges (green/amber/red); cards with `hydration_status='partial'` or `'failed'` show `⚠ JD incomplete` indicator. Events instrumentation hooks into every UI interaction writing to `events` table.
- **Dependencies**: TASK-M1-009
- **Implementation Checklist**:
  - Schema: writes `events` (one row per interaction)
  - Wire: `src/jd_matcher/web/templates/main.html` (extends base); `src/jd_matcher/web/static/js/app.js` (keyboard handlers); event-write endpoint in routes.py
  - Call site: keyboard handlers POST to event-write endpoint; HTMX swaps trigger event emission
  - Imports affected: routes.py adds event-write endpoint
  - Runtime files: templates + static assets
- **Demo Artifact**: User opens `http://localhost:8765/`, navigates with `j/k`, expands with `e`, dismisses with `d` (sees slide-left animation), switches tabs with `1/2/3`; `sqlite3 ... "SELECT type, count(*) FROM events GROUP BY type"` shows event counts matching interactions.
- **Quality log**: `docs/poc/quality-logs/TASK-M1-010.md`
- **Acceptance Criteria**:
  - [x] Three tabs (Main / Applied / Dismissed) render correctly with seeded fixture postings
  - [x] Keyboard shortcuts work: `j`/`k` (next/prev card), `e` (expand), `d` (dismiss with 180ms slide-left), `a` (mark applied), `o` (open URL in new tab), `1`/`2`/`3` (switch tabs), `?` (cheatsheet overlay), `Esc` (close cheatsheet/collapse expanded card)
  - [x] Sub-bar shows 4 health badges: `LI-email`, `IN-email`, `LI-hydrate`, `IN-hydrate` — colors per `/api/source-health`
  - [x] Health badges are NOT dismissible (no close button); auto-clear only when `/api/source-health` reports the source returned to `healthy`
  - [x] Hover on a non-green badge shows `failure_reason` tooltip
  - [x] Cards with `hydration_status='partial'` or `'failed'` show inline `⚠ JD incomplete` indicator on line 2; all keyboard shortcuts (`e`/`d`/`a`/`o`) still work on these cards
  - [x] Events instrumentation: every interaction (`card_viewed`, `card_expanded`, `card_dismissed`, `card_marked_applied`, `sync_triggered`, `sync_completed`, `tab_switched`, `card_restored`) writes exactly one correctly-typed row to `events` with `time_to_decide_ms` (where applicable) and `session_id`
  - [x] Structural DOM tests with Playwright (or equivalent) — 100% pass

---

##### TASK-M1-011 — Real-data validation against live email samples

- **Status**: Done (2026-04-27)
- **Blocked reason**:
- **Agent**: test-validator (with user collaboration to provide real samples)
- **Component**: validates C3 (Gmail), C4 (URL parser), C5 (Hydrator) — TDD §C3, §C4, §C5
- **Description**: Run the parsing and hydration pipeline against real LinkedIn + Indeed alert emails the user has accumulated since SETUP completion. Compute extraction and hydration accuracy. Update PoC quality logs. This is the Gate 4 real-data validation.
- **Dependencies**: TASK-M1-002, TASK-M1-008
- **Implementation Checklist**:
  - Schema: N/A (validation only, reads from existing tables)
  - Wire: `tests/validation/test_real_data.py` (new) — parametrized over real samples
  - Call site: `pytest tests/validation/test_real_data.py --real-samples=<path>`
  - Imports affected: N/A
  - Runtime files: real samples staged at `tests/fixtures/real/` (gitignored — these contain sensitive job-search data)
- **Demo Artifact**: `docs/poc/quality-logs/TASK-M1-011.md` documenting per-source extraction rate (should be ≥95%) + hydration rate (should be ≥95%) + sample-level details + any failure modes encountered.
- **Quality log**: `docs/poc/quality-logs/TASK-M1-011.md`
- **Acceptance Criteria**:
  - [x] Sample size: ≥50 real LinkedIn alert emails + ≥30 real Indeed alert emails
  - [x] LinkedIn URL extraction rate ≥95% (per PRD SC-1, ROADMAP M1 AC)
  - [x] Indeed URL extraction rate ≥95% (per PRD SC-2)
  - [x] JD hydration rate ≥95% on ≥30 real URLs (per PRD SC-3)
  - [x] Quality log includes per-failure reason categorization (which samples failed and why)
  - [x] Any source falling below 95% triggers Major-tier root-cause analysis per CLAUDE.md Gate 5
  - [x] Real samples gitignored — never committed (sensitive content)

---

##### TASK-M1-012 — M1 demo + user approval

- **Status**: Done (2026-04-27)
- **Blocked reason**:
- **Agent**: manual (user)
- **Component**: M1 milestone deliverable acceptance — references all C-components
- **Description**: User runs the system on real data for 1-2 days and validates per the user-validation checklist. PHASE-REVIEW.md updated; M1 ACs confirmed met; user signs off.
- **Dependencies**: TASK-M1-010, TASK-M1-011
- **Implementation Checklist**:
  - Schema: N/A
  - Wire: N/A
  - Call site: N/A
  - Imports affected: N/A
  - Runtime files: `docs/poc/PHASE-REVIEW.md` (or appended note) — user feedback + sign-off
- **Demo Artifact**: User has triaged ≥1 real day's postings end-to-end; written sign-off in PHASE-REVIEW.md.
- **Quality log**: `docs/poc/quality-logs/TASK-M1-012.md`
- **Acceptance Criteria**:
  - [x] User has run the system on ≥1 day of real LinkedIn + Indeed alert emails
  - [x] Coverage check: card count matches unique URL count from emails (or close, accounting for URL dedup)
  - [x] Spot-check ≥3 cards: title/company match emails; click-through to source URL works; JD on card matches JD on source page
  - [x] State persistence check: after restart, applied/dismissed postings do not reappear in Main
  - [x] Source-health badges visible and accurate (all green when sources healthy)
  - [x] User confirms M1 deliverable meets the goal in PHASE-REVIEW.md or written confirmation
  - [x] Quality logs from M1-001 through M1-011 are present and reviewed

---

## Invalidated Tasks

<!-- Tasks invalidated by a direction change. Preserved for audit trail. -->
<!-- Copy block below for each invalidated task. -->

<!--
### TASK-XXX — [Title]
- **Invalidated**: YYYY-MM-DD
- **Reason**: [Direction change — one sentence]
- **Original status**: Done | In Progress | To Do
-->
