# Quality Log — TASK-M2-001
**Schema migration (4 new tables + email_ingest_log delta)**
**Date**: 2026-04-27

---

## Demo Artifact — `.schema` output

```
CREATE TABLE canonical_postings (
    canonical_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT NOT NULL DEFAULT 'default' REFERENCES users(id),
    canonical_title     TEXT NOT NULL,
    canonical_company   TEXT NOT NULL,
    canonical_seniority TEXT NOT NULL,
    canonical_location  TEXT NOT NULL,
    team_or_department  TEXT NULL,
    top_skills          JSON NOT NULL,
    role_summary        TEXT NOT NULL,
    full_jd             TEXT NOT NULL,
    full_jd_provenance  JSON NOT NULL,
    first_seen          TIMESTAMP NOT NULL,
    last_seen           TIMESTAMP NOT NULL,
    sources_summary     JSON NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at          TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX idx_canonical_user_block      ON canonical_postings (user_id, canonical_company, team_or_department, canonical_location);
CREATE INDEX idx_canonical_user_first_seen ON canonical_postings (user_id, first_seen DESC);

CREATE TABLE posting_canonical_links (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          TEXT NOT NULL DEFAULT 'default' REFERENCES users(id),
    posting_id       TEXT NOT NULL,
    canonical_id     INTEGER NOT NULL,
    similarity_score REAL NOT NULL,
    merge_kind       TEXT NOT NULL,
    merged_at        TIMESTAMP NOT NULL,
    UNIQUE (user_id, posting_id)
);
CREATE INDEX idx_links_canonical ON posting_canonical_links (canonical_id);
CREATE INDEX idx_links_posting   ON posting_canonical_links (posting_id);
CREATE INDEX idx_links_repost    ON posting_canonical_links (canonical_id, merge_kind);

CREATE TABLE posting_embeddings (
    posting_id      TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL DEFAULT 'default' REFERENCES users(id),
    text_source     TEXT NOT NULL,
    text_hash       TEXT NOT NULL,
    embedding       BLOB NOT NULL,
    embedding_dim   INTEGER NOT NULL,
    model_name      TEXT NOT NULL,
    embedded_at     TIMESTAMP NOT NULL
);
CREATE INDEX idx_embeddings_user_model ON posting_embeddings (user_id, model_name);

CREATE TABLE llm_call_ledger (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT NOT NULL DEFAULT 'default' REFERENCES users(id),
    provider      TEXT NOT NULL,
    model_name    TEXT NOT NULL,
    call_kind     TEXT NOT NULL,
    input_tokens  INTEGER NULL,
    output_tokens INTEGER NULL,
    cost_usd      REAL NOT NULL DEFAULT 0.0,
    latency_ms    INTEGER NOT NULL,
    posting_id    TEXT NULL,
    called_at     TIMESTAMP NOT NULL,
    status        TEXT NOT NULL
);
CREATE INDEX idx_ledger_user_called ON llm_call_ledger (user_id, called_at DESC);
CREATE INDEX idx_ledger_user_kind   ON llm_call_ledger (user_id, call_kind, model_name);

-- email_ingest_log (filter columns + index — applied via Python ALTER TABLE helper)
-- PRAGMA table_info output: filter_status TEXT col 15, filter_reason TEXT col 16
CREATE INDEX idx_email_ingest_log_filter ON email_ingest_log (filter_status);
```

---

## Acceptance Criteria Verification

- [x] All 4 new tables created via `CREATE TABLE IF NOT EXISTS` (idempotent) — confirmed via `.schema` output above; all 4 tables present.
- [x] `email_ingest_log` gains `filter_status TEXT NULL` + `filter_reason TEXT NULL` + `idx_email_ingest_log_filter` — PRAGMA table_info shows cols 15 and 16; index confirmed in sqlite_master.
- [x] All canonical-related indexes created; `idx_canonical_user_block` uses `(user_id, canonical_company, team_or_department, canonical_location)` — confirmed in `.schema` output.
- [x] `init_db()` re-run on populated DB preserves all data, no errors — test `test_idempotency_on_populated_db` passes; real-DB row counts unchanged (see below).
- [x] Test: each new table exists with expected columns + indexes — `test_all_4_new_tables_exist`, `test_all_8_new_indexes_exist`, `test_email_ingest_log_has_filter_columns` all pass.
- [x] Test: re-running `init_db` on a populated DB doesn't drop or error — `test_idempotency_on_populated_db` passes.

---

## Pytest Summary

```
21 passed, 0 failed
```

Tests added:
- `tests/db/test_init_db_m2.py::test_all_4_new_tables_exist`
- `tests/db/test_init_db_m2.py::test_all_8_new_indexes_exist`
- `tests/db/test_init_db_m2.py::test_posting_canonical_links_unique_user_posting`
- `tests/db/test_init_db_m2.py::test_email_ingest_log_has_filter_columns`
- `tests/db/test_init_db_m2.py::test_filter_columns_nullable`
- `tests/db/test_init_db_m2.py::test_idempotency_on_populated_db`

Existing tests updated:
- `tests/db/test_init_db.py::test_init_db_creates_all_tables` (renamed from `_all_8_tables`; ALL_TABLES set extended to 13 tables)

---

## Real DB Idempotency — Row Counts Before/After Migration

Migration applied to `~/.jd-matcher/jd-matcher.db` (existing populated DB from M1):

| Table             | Before | After | Status |
|-------------------|--------|-------|--------|
| postings          | 91     | 91    | PRESERVED |
| email_ingest_log  | 56     | 56    | PRESERVED |
| applied           | 0      | 0     | PRESERVED |
| dismissed         | 0      | 0     | PRESERVED |

All existing data intact. New tables created empty as expected.

---

## Implementation Notes

- `idx_email_ingest_log_filter` is created in `init_db.py` via `_ensure_email_ingest_log_filter_columns()` rather than in `schema.sql`. Reason: `executescript` runs `schema.sql` before the `ALTER TABLE` helper adds the columns; SQLite would raise `no such column: filter_status` if the index DDL appeared in `schema.sql` on a fresh DB.
- `idx_canonical_user_first_seen` uses explicit `DESC` ordering per TDD spec (optimises `ORDER BY first_seen DESC` Main view query).
- `posting_embeddings.posting_id TEXT PRIMARY KEY` matches TDD spec (TEXT, not INTEGER — postings.id is INTEGER but the FK is stored as TEXT per spec).

---

## Independent Validation (test-validator, 2026-04-27)

**Validator**: test-validator agent (Claude Sonnet 4.6)

### Unit Tests
- DB tests: 21 passed, 0 failed (`tests/db/` — all 3 test files collected and run)
- Broader suite (excluding tests with uninstalled deps): 246 passed, 2 failed, 18 skipped
  - 2 pre-existing failures in `tests/ingest/test_gmail.py` due to missing `google.auth` / `googleapiclient` packages — unrelated to TASK-M2-001, pre-date this task

### Fresh DB Verification (independent sqlite_master query)
- Tables (13 total): applied, canonical_postings, dismissed, email_ingest_log, events, llm_call_ledger, pipeline_runs, posting_canonical_links, posting_embeddings, posting_sources, postings, seen_urls, users — all 4 new M2 tables present
- Indexes (15 total, excluding sqlite auto-indexes): all 8 required M2 indexes present — idx_canonical_user_block, idx_canonical_user_first_seen, idx_email_ingest_log_filter, idx_embeddings_user_model, idx_ledger_user_called, idx_ledger_user_kind, idx_links_canonical, idx_links_posting, idx_links_repost
- email_ingest_log columns 15+16: filter_status TEXT NULL, filter_reason TEXT NULL — confirmed present

### Populated DB Idempotency (independent test)
- 3 postings, 2 email_ingest_log, 1 canonical_postings, 1 posting_canonical_links inserted
- Second `init_db()` call: no exception raised
- Row counts: identical before and after (3/2/1/1)
- Column count (email_ingest_log): 17 before and after — unchanged
- Index set: identical before and after — no duplicate indexes created

### CHECK Constraint Observation (Step 5)
- `posting_canonical_links.merge_kind` has no DB-level CHECK constraint; invalid values are silently accepted
- All 3 valid values ('new_canonical', 'content_dedup', 'repost') accepted correctly
- Observation only — TDD does not strictly require a CHECK constraint; validation expected in Python layer

### Real DB Verification (read-only)
- Tables: all 13 present (4 new M2 tables confirmed)
- email_ingest_log: filter_status at col 15, filter_reason at col 16 — both TEXT NULL
- Row counts: postings=91, email_ingest_log=56, applied=0, dismissed=0 — match implementer's report exactly

### Per-AC Verdicts
- AC #1 (4 new tables idempotent): PASS
- AC #2 (filter_status / filter_reason / idx): PASS
- AC #3 (canonical indexes correct): PASS
- AC #4 (idempotent on populated DB): PASS
- AC #5 (test: tables exist + indexes): PASS
- AC #6 (test: re-init populated DB safe): PASS

**Overall: PASS — no issues found**
