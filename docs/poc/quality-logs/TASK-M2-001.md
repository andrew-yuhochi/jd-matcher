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
