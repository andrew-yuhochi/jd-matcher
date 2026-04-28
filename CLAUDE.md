# jd-matcher
A local-only desktop tool that consolidates job postings from LinkedIn, Indeed, Job Bank Canada, and several open-API sources into a single browser-based daily-triage workflow — content-aware dedup, LLM role-fit filtering, technical-focus tagging, and CV-variant recommendation for a Vancouver-based DS/ML engineer actively job-hunting.

---

## Current State

| | |
|-|-|
| **Phase** | PoC |
| **Milestone** | M2 — Content-aware dedup + repost detection (+ title pre-filter) |
| **Last completed** | TASK-M2-005 — LLM Provider Abstraction (C28) (Done 2026-04-27) |
| **In Progress** | TASK-M2-004 + TASK-M2-006 — both re-opened 2026-04-28 for re-validation against expanded 156-posting dataset (was 91 / 71 originally) |
| **Next task** | Re-validate M2-004 (filter) + M2-006 (extraction) on the new 65 postings, then TASK-M2-007 |
| **Next command** | (interactive validation in main session — no /implement until both close) |
| **Scope note** | Indeed extraction deferred to MVP-M1 per ALIGNMENT-LOG 2026-04-28 / PRD §9 R3. PoC = LinkedIn-only. browser_fetcher.py infrastructure committed (`ce7def0`) and ready for MVP reactivation. |

---

## Local environment

This project ships with a venv at `.venv/` (Python 3.11). Bare `python` on this machine resolves to pyenv 3.14 which lacks `google.auth`/`googleapiclient` and will produce false test failures. **Always run pytest as `.venv/bin/python -m pytest …`** (or `source .venv/bin/activate` first).

### Data safety
- Local DB: `~/.jd-matcher/jd-matcher.db`. Wiped 2026-04-28 by an unidentified subagent/sandbox interaction; recovered via Gmail re-ingest + LLM re-extraction (~$0.07).
- Recovery snapshot: `~/.jd-matcher/snapshots/jd-matcher-recovery-2026-04-28-1556.db` (atomic SQLite .backup, ~42MB).
- **Before any destructive DB operation in future**: snapshot first via `sqlite3 ~/.jd-matcher/jd-matcher.db ".backup ~/.jd-matcher/snapshots/$(date +%Y%m%d-%H%M).db"`. Daily backup cron is a backlog item.

---

## Documents

### Discovery
- Roadmap: `docs/discovery/ROADMAP.md`
- Requirements: `docs/discovery/DISCOVERY-NOTES.md`
- Market analysis: `docs/discovery/MARKET-ANALYSIS.md`
- Research: `docs/discovery/RESEARCH-REPORT.md`
- UX: `docs/discovery/UX-SPEC.md`
- Design brief: `docs/discovery/designs/main-page-brief.md`

### Current Phase (PoC)
- PRD: `docs/poc/PRD.md`
- TDD: `docs/poc/TDD.md` (Part 1; Part 2 filled during /milestone-plan)
- Data sources: `docs/poc/DATA-SOURCES.md`
- UX: `docs/poc/UX-SPEC.md`
- Alignment log: `docs/poc/ALIGNMENT-LOG.md`
- Design gate review: `docs/poc/DESIGN-GATE-REVIEW.md`
- Tasks: `docs/poc/TASKS.md` _(populated by /milestone-plan)_
- Backlog: `docs/poc/BACKLOG.md` _(populated by /milestone-plan)_
- Quality logs: `docs/poc/quality-logs/` _(populated per task)_
