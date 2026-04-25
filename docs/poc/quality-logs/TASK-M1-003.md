# Quality Log — TASK-M1-003 — Data model + idempotent init_db

**Date**: 2026-04-24
**Agent**: data-pipeline
**Evaluation type**: Deterministic (structural schema correctness)
**Pass threshold**: 100% on all test cases

## Test results

| Test | Result |
|------|--------|
| test_init_db_creates_database | PASS |
| test_init_db_creates_all_8_tables | PASS |
| test_init_db_idempotent | PASS |
| test_init_db_user_id_present_on_every_table | PASS |
| test_postings_hydration_status_check | PASS |
| test_pipeline_runs_health_status_check | PASS |
| test_seen_urls_unique_constraint | PASS |
| test_applied_dismissed_unique_per_posting | PASS |
| test_smoke_insert_and_query | PASS |

**Total**: 9/9 passed (100%)

## Demo artifact output

```
['applied', 'dismissed', 'events', 'pipeline_runs', 'posting_sources', 'postings', 'seen_urls', 'sqlite_sequence', 'users']
```

(`sqlite_sequence` is SQLite's internal autoincrement tracker — not an application table.)

## Minor auto-fixes applied

1. Test `test_init_db_creates_all_8_tables`: added filter to exclude `sqlite_sequence` from the table set comparison — SQLite creates this automatically when any `AUTOINCREMENT` column is present.
2. Test `test_init_db_user_id_present_on_every_table`: excluded the `users` table from the `user_id` column check — `users` is the identity anchor table; it has `id` (PRIMARY KEY), not `user_id`. All 7 other tables carry `user_id NOT NULL DEFAULT 'default'`.

## Schema design notes

- `users.id` is `TEXT PRIMARY KEY` (not `INTEGER`) to allow named namespaces in future (hedge 3).
- `seen_urls` UNIQUE constraint is on `(user_id, url)` — also satisfies the FK lookup without a separate index.
- `pipeline_runs.health_status` is `NOT NULL` with a `CHECK` constraint — failures cannot be hidden (C11 invariant enforced at the schema level).

---

## Independent Validation Report (test-validator)
Date: 2026-04-24

| AC | Status | Evidence |
|----|--------|----------|
| AC1 8 tables w/ documented columns+types | PASS | Tables: applied, dismissed, events, pipeline_runs, posting_sources, postings, seen_urls, users (sqlite_sequence excluded). All checked columns present in every table per TDD §C2. |
| AC2 user_id on every table (except users) | PASS | PRAGMA table_info confirmed user_id TEXT NOT NULL dflt='default' on all 7 non-users tables. users table intentionally has id (PRIMARY KEY), not user_id — consistent with TDD §C2 design note. TASKS.md AC text ("every table") is technically imprecise; the schema note and data-pipeline exclusion are correct per the TDD spec. Logged as a Minor spec-wording issue. |
| AC3 postings.hydration_status CHECK | PASS | INSERT 'bad' raised IntegrityError. INSERT 'complete', 'partial', 'failed' all committed successfully. |
| AC4 pipeline_runs.health_status CHECK | PASS | INSERT 'unknown' raised IntegrityError. INSERT 'healthy', 'degraded', 'failed' all committed successfully. |
| AC5 init_db idempotent | PASS | Called init_db() twice on same db_path; no exception; users table count = 1 after both calls. |
| AC6 UNIQUE constraints | PASS | seen_urls UNIQUE(user_id, url): duplicate (same user_id + url) raises IntegrityError; same url with different user_id succeeds (correct composite behaviour per TDD). applied UNIQUE(user_id, posting_id): duplicate raises IntegrityError. dismissed UNIQUE(user_id, posting_id): duplicate raises IntegrityError. Note: TASKS.md AC6 lists seen_urls.url as a single-column unique; actual implementation is UNIQUE(user_id, url) per TDD §C2 — the composite is correct for multi-user namespace. Logged as a Minor spec-wording discrepancy in TASKS.md. |
| AC7 Indexes present | PASS | idx_postings_first_seen on postings.first_seen — verified via PRAGMA index_info. idx_events_timestamp on events.timestamp — verified. idx_pipeline_runs_run_id on pipeline_runs.run_id — verified. idx_posting_sources_posting_id on posting_sources.posting_id — verified (present in schema; not listed in TASKS.md AC7 but present in TDD §C2 quality criteria — no issue). |
| AC8 Smoke insert test | PASS | Inserted posting + posting_source + seen_url + applied row; SELECT roundtrip: canonical_company='Smoke Corp', canonical_title='ML Engineer', applied.status='Applied', seen_urls.posting_id matches. FK chain intact. |

Foreign-key enforcement: ON — PRAGMA foreign_keys returns 1; FK violation (insert posting_source with non-existent posting_id=999999) raises IntegrityError confirming enforcement is active, not just declared.

Default user row: users table contains exactly 1 row with id='default' after init_db().

Unit tests: 9 passed, 0 failed (required: 100%) — all tests complete in 0.10s, no test exceeds 1s.

### Notes (not blocking)

1. **Minor — spec wording, TASKS.md AC2**: "Every table has user_id" is imprecise — the `users` table is the identity anchor and correctly uses `id` as its PK. The implementation and data-pipeline exclusion are correct per TDD §C2. TASKS.md should read "Every table except `users`". No code change needed.

2. **Minor — spec wording, TASKS.md AC6**: AC6 lists `seen_urls.url` as a single-column UNIQUE. The actual constraint is `UNIQUE(user_id, url)` (composite), which is correct per TDD §C2 schema notes and allows multi-user namespacing. TASKS.md wording should be updated to reflect the composite key. No code change needed.

3. **Observation — TASKS.md AC7**: Only 3 indexes listed; schema implements 4 (adds `idx_posting_sources_posting_id`). The 4th index is present in TDD §C2 quality criteria as implicit via the FK and is a sound addition. Not a defect.

Overall verdict: PASS
