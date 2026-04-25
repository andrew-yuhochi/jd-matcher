# Tasks — jd-matcher — PoC

> **Phase**: PoC
> **Last Updated**: 2026-04-24

---

## Progress Summary
- Done: 5 | In Progress: 0 | To Do: 7 | Blocked: 0
- Current milestone: M1
- Invalidated tasks: 0

---

## Milestone 1 — Raw pipe + URL dedup + applied/dismissed state

**Goal**: Working local pipeline + browser UI showing today's fresh LinkedIn + Indeed jobs with state tracking.
**Deliverable**: User runs `python -m jd_matcher`, opens `localhost:8765`, triages real postings via keyboard, returns next day to find no reappearance of handled cards.
**Review checkpoint**: User approves deliverable before M2 begins.

---

### TASK-M1-001 — Repo bootstrap + project skeleton

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

### TASK-M1-002 — SETUP.md + saved-search keyword discussion

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

### TASK-M1-003 — Data model + idempotent init_db

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

### TASK-M1-004 — Gmail ingester (OAuth + fetch)

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

### TASK-M1-005 — Email URL parsers + URL-based dedup

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

### TASK-M1-006 — JD hydrator (LinkedIn + Indeed guest endpoints)

- **Status**: To Do
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
  - [ ] 100% JD extraction on 10 LinkedIn + 10 Indeed synthetic HTML fixtures
  - [ ] Rate limiter measurably enforces 1 request per 30 seconds across the entire process (not per-instance)
  - [ ] Per-URL failure path: posting still inserted with `hydration_status='failed'` and `posting_sources.raw_html='ERROR: <reason>'`; logged but not raised
  - [ ] Source-level health threshold: >20% per-run fail → next `pipeline_runs` row for that source has `health_status='degraded'`
  - [ ] 100% per-run fail → `pipeline_runs.health_status='failed'`, `failure_reason='rate_limit'` if all errors are 429, else exception text
  - [ ] Hydrated `raw_html` cached in `posting_sources.raw_html` — never re-fetched for same URL
  - [ ] No silent drops verified by integration test: feed 5 URLs (3 success + 2 fail), assert 5 postings end up in `postings` with correct `hydration_status`

---

### TASK-M1-007 — State manager (applied / dismissed / restore)

- **Status**: To Do
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
  - [ ] `mark_applied(posting_id)` creates a row in `applied` with current timestamp and `status='Applied'` (default)
  - [ ] `dismiss(posting_id)` creates a row in `dismissed` with current timestamp; idempotent (re-dismiss is no-op)
  - [ ] `restore(posting_id)` deletes from `dismissed`; if not in dismissed, no-op
  - [ ] `main_view_postings()` returns postings WHERE `id NOT IN (SELECT posting_id FROM applied) AND id NOT IN (SELECT posting_id FROM dismissed)` — verified against fixture
  - [ ] State persists across server restart (integration test closes connection, reopens, reads)
  - [ ] `auto_remove_stale_applied(cutoff_date)` exists and is unit-tested — but not auto-triggered in M1 (scheduler is MVP)

---

### TASK-M1-008 — Pipeline orchestrator + non-hideable health logging

- **Status**: To Do
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
  - [ ] One `pipeline_runs` row per source per run, with non-null `health_status` — verified by integration test that runs pipeline 3 times and asserts 12 rows total
  - [ ] Per-source isolation: integration test forces failure in `hydrator_linkedin` (mock raises) → `gmail_linkedin`, `gmail_indeed`, `hydrator_indeed` still complete with `health_status='healthy'`
  - [ ] Health transition emits `source_failure` event in `events` table — fields: `source`, `previous_status`, `new_status`, `failure_reason`, `timestamp`
  - [ ] Structured JSON log written to `logs/pipeline-<run_id>.jsonl` — one line per pipeline step
  - [ ] End-to-end fixture run: feeding 5 LinkedIn + 5 Indeed fixture emails produces N postings in `postings` table where N matches expected unique URL count
  - [ ] Idempotency: re-running on same fixture mailbox produces 0 new postings (URL dedup respected)

---

### TASK-M1-009 — Web UI backend (FastAPI + 8 endpoints + source-health)

- **Status**: To Do
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
  - [ ] All 8 endpoints respond per contract: `GET /` (Main HTML), `GET /applied` (Applied HTML), `GET /dismissed` (Dismissed HTML), `POST /sync`, `POST /postings/{id}/dismiss`, `POST /postings/{id}/apply`, `POST /postings/{id}/restore`, `GET /healthz`, `GET /api/source-health` (JSON)
  - [ ] `GET /api/source-health` returns latest per-source state from `pipeline_runs` — schema: `[{source, status, last_run, last_success}, ...]`
  - [ ] Main view query does NOT filter by `hydration_status` — postings with `partial`/`failed` hydration appear (verified by test that seeds 3 hydration-failed postings + asserts they appear in Main HTML response)
  - [ ] Bind address is exclusively `127.0.0.1` — `0.0.0.0` rejected (configurable but defaulted to 127.0.0.1; integration test verifies)
  - [ ] State-mutation endpoints (`/apply`, `/dismiss`, `/restore`) are idempotent — calling twice produces same DB state
  - [ ] All endpoints have integration tests with seeded fixture DB; 100% pass

---

### TASK-M1-010 — Web UI frontend + events instrumentation

- **Status**: To Do
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
  - [ ] Three tabs (Main / Applied / Dismissed) render correctly with seeded fixture postings
  - [ ] Keyboard shortcuts work: `j`/`k` (next/prev card), `e` (expand), `d` (dismiss with 180ms slide-left), `a` (mark applied), `o` (open URL in new tab), `1`/`2`/`3` (switch tabs), `?` (cheatsheet overlay), `Esc` (close cheatsheet/collapse expanded card)
  - [ ] Sub-bar shows 4 health badges: `LI-email`, `IN-email`, `LI-hydrate`, `IN-hydrate` — colors per `/api/source-health`
  - [ ] Health badges are NOT dismissible (no close button); auto-clear only when `/api/source-health` reports the source returned to `healthy`
  - [ ] Hover on a non-green badge shows `failure_reason` tooltip
  - [ ] Cards with `hydration_status='partial'` or `'failed'` show inline `⚠ JD incomplete` indicator on line 2; all keyboard shortcuts (`e`/`d`/`a`/`o`) still work on these cards
  - [ ] Events instrumentation: every interaction (`card_viewed`, `card_expanded`, `card_dismissed`, `card_marked_applied`, `sync_triggered`, `sync_completed`, `tab_switched`, `card_restored`) writes exactly one correctly-typed row to `events` with `time_to_decide_ms` (where applicable) and `session_id`
  - [ ] Structural DOM tests with Playwright (or equivalent) — 100% pass

---

### TASK-M1-011 — Real-data validation against live email samples

- **Status**: To Do
- **Blocked reason**: Awaits user accumulating ≥50 LinkedIn + ≥30 Indeed real alert emails post-TASK-M1-002 setup
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
  - [ ] Sample size: ≥50 real LinkedIn alert emails + ≥30 real Indeed alert emails
  - [ ] LinkedIn URL extraction rate ≥95% (per PRD SC-1, ROADMAP M1 AC)
  - [ ] Indeed URL extraction rate ≥95% (per PRD SC-2)
  - [ ] JD hydration rate ≥95% on ≥30 real URLs (per PRD SC-3)
  - [ ] Quality log includes per-failure reason categorization (which samples failed and why)
  - [ ] Any source falling below 95% triggers Major-tier root-cause analysis per CLAUDE.md Gate 5
  - [ ] Real samples gitignored — never committed (sensitive content)

---

### TASK-M1-012 — M1 demo + user approval

- **Status**: To Do
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
  - [ ] User has run the system on ≥1 day of real LinkedIn + Indeed alert emails
  - [ ] Coverage check: card count matches unique URL count from emails (or close, accounting for URL dedup)
  - [ ] Spot-check ≥3 cards: title/company match emails; click-through to source URL works; JD on card matches JD on source page
  - [ ] State persistence check: after restart, applied/dismissed postings do not reappear in Main
  - [ ] Source-health badges visible and accurate (all green when sources healthy)
  - [ ] User confirms M1 deliverable meets the goal in PHASE-REVIEW.md or written confirmation
  - [ ] Quality logs from M1-001 through M1-011 are present and reviewed

---

## Completed Milestones Log

| Milestone | Closed | Quality | Alignment | Notes |
|-----------|--------|---------|-----------|-------|
| | | | | |

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
