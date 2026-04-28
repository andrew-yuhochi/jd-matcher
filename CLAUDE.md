# jd-matcher
A local-only desktop tool that consolidates job postings from LinkedIn, Indeed, Job Bank Canada, and several open-API sources into a single browser-based daily-triage workflow — content-aware dedup, LLM role-fit filtering, technical-focus tagging, and CV-variant recommendation for a Vancouver-based DS/ML engineer actively job-hunting.

---

## Current State

| | |
|-|-|
| **Phase** | PoC |
| **Milestone** | M2 — Content-aware dedup + repost detection (+ title pre-filter) |
| **Last completed** | TASK-M2-006 — LLM Extraction (C18) — strict canonical labels (Done 2026-04-27) |
| **Next task** | TASK-M2-007 — Embedding Pipeline (C20) [data-pipeline] |
| **Next command** | /implement jd-matcher TASK-M2-007 |

---

## Local environment

This project ships with a venv at `.venv/` (Python 3.11). Bare `python` on this machine resolves to pyenv 3.14 which lacks `google.auth`/`googleapiclient` and will produce false test failures. **Always run pytest as `.venv/bin/python -m pytest …`** (or `source .venv/bin/activate` first).

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
