# Quality Log — TASK-M3-001
# Schema migration: 11 new columns on canonical_postings + sort index

**Date**: 2026-05-01
**Agent**: data-pipeline
**Component**: C2 (Schema)

---

## Snapshot

Taken before any live DB changes:

```
~/.jd-matcher/snapshots/20260501-0952-pre-m3-001-schema.db
```

---

## Migration tuples added to `_COLUMN_MIGRATIONS`

Appended to `src/jd_matcher/db/init_db.py` (11 new entries after the M2-013 block):

```python
# M3-001: LLM-extracted classification fields on canonical_postings (C18 v2)
("canonical_postings", "fit_score",
 "ALTER TABLE canonical_postings ADD COLUMN fit_score INTEGER NULL CHECK (fit_score BETWEEN 1 AND 5);"),

("canonical_postings", "fit_reasoning",
 "ALTER TABLE canonical_postings ADD COLUMN fit_reasoning TEXT NULL;"),

("canonical_postings", "industry",
 "ALTER TABLE canonical_postings ADD COLUMN industry TEXT NULL CHECK (industry IN (...16 sectors...));"),

("canonical_postings", "role_orientation",
 "ALTER TABLE canonical_postings ADD COLUMN role_orientation TEXT NULL;"),  # Pydantic-layer validation

("canonical_postings", "salary_min_cad",
 "ALTER TABLE canonical_postings ADD COLUMN salary_min_cad INTEGER NULL;"),

("canonical_postings", "salary_max_cad",
 "ALTER TABLE canonical_postings ADD COLUMN salary_max_cad INTEGER NULL;"),

("canonical_postings", "citizenship_requirement",
 "ALTER TABLE canonical_postings ADD COLUMN citizenship_requirement TEXT NULL "
 "CHECK (citizenship_requirement IN ('required', 'preferred', 'not_mentioned'));"),

("canonical_postings", "citizenship_reason",
 "ALTER TABLE canonical_postings ADD COLUMN citizenship_reason TEXT NULL;"),

("canonical_postings", "can_hire_in_canada",
 "ALTER TABLE canonical_postings ADD COLUMN can_hire_in_canada TEXT NULL "
 "CHECK (can_hire_in_canada IN ('yes', 'likely', 'no', 'unclear'));"),

# M3-001: Hard-filter fields (C33, populated at TASK-M3-006)
("canonical_postings", "is_filtered",
 "ALTER TABLE canonical_postings ADD COLUMN is_filtered BOOLEAN NOT NULL DEFAULT 0;"),

("canonical_postings", "filter_reason",
 "ALTER TABLE canonical_postings ADD COLUMN filter_reason TEXT NULL;"),
```

---

## Index added to `_INDEX_MIGRATIONS`

```python
"CREATE INDEX IF NOT EXISTS idx_canonical_user_main_rank "
"ON canonical_postings(user_id, fit_score DESC, salary_max_cad DESC);"
```

Covers the leading stored columns of the C34 4-tuple sort `(fit_score DESC, orientation_diversity DESC, salary_max_cad DESC, post_date DESC)`. `orientation_diversity` is computed from `role_orientation` at query time — not stored — so the index covers the materialized prefix only.

---

## Test counts

| | Count |
|-|-------|
| Before (M3-000b baseline) | 979 |
| New tests added (test_init_db_m3.py) | 14 |
| After | 993 passed, 10 skipped |

New test file: `tests/db/test_init_db_m3.py`

Tests cover:
- All 11 columns present after migration
- `idx_canonical_user_main_rank` in `sqlite_master`
- `fit_score` CHECK: rejects 0, rejects 6, accepts 1-5, accepts NULL
- `citizenship_requirement` CHECK: rejects 'unknown', accepts all 3 valid values
- `can_hire_in_canada` CHECK: rejects 'maybe', accepts all 4 valid values
- `industry` CHECK: rejects 'Invalid Sector', accepts all 16 valid sectors
- `is_filtered` defaults to 0
- Idempotency: running `init_db` twice produces no schema drift

---

## Live DB verification

```
# Schema shows all 11 new columns
sqlite3 ~/.jd-matcher/jd-matcher.db ".schema canonical_postings"
→ fit_score INTEGER NULL CHECK (fit_score BETWEEN 1 AND 5),
  fit_reasoning TEXT NULL,
  industry TEXT NULL CHECK (industry IN ('Financial Services / Asset Management',...,'Other')),
  role_orientation TEXT NULL,
  salary_min_cad INTEGER NULL,
  salary_max_cad INTEGER NULL,
  citizenship_requirement TEXT NULL CHECK (citizenship_requirement IN ('required','preferred','not_mentioned')),
  citizenship_reason TEXT NULL,
  can_hire_in_canada TEXT NULL CHECK (can_hire_in_canada IN ('yes','likely','no','unclear')),
  is_filtered BOOLEAN NOT NULL DEFAULT 0,
  filter_reason TEXT NULL

# Index present
sqlite3 ~/.jd-matcher/jd-matcher.db ".indexes canonical_postings"
→ idx_canonical_user_block  idx_canonical_user_first_seen  idx_canonical_user_main_rank

# Canonical count unchanged
sqlite3 ~/.jd-matcher/jd-matcher.db "SELECT COUNT(*) FROM canonical_postings;"
→ 257

# Idempotency: second init_db() call
→ "Second init_db OK — idempotent"
```

---

## Auto-fixes applied

None. Zero Minor fixes required — migration applied cleanly on first attempt.

---

## Independent Validation — test-validator (2026-04-30)

### Full test suite run
```
SKIP_LIVE=1 .venv/bin/python -m pytest -v
993 passed, 10 skipped, 31 warnings in 32.23s
```
Zero failures. 10 skips are pre-existing (live-network tests gated by SKIP_LIVE=1).

### M3-001 test file in isolation
```
SKIP_LIVE=1 .venv/bin/python -m pytest -v tests/db/test_init_db_m3.py
14 passed in 0.18s
```

### AC verdicts

| AC | Verdict | Evidence |
|----|---------|----------|
| AC1: All 11 columns present | PASS | `PRAGMA table_info(canonical_postings)` returns 27 rows (16 pre-existing + 11 new); all 11 column names confirmed via live DB + `_COLUMN_MIGRATIONS` list inspection |
| AC2: `idx_canonical_user_main_rank` exists and used by query planner | PASS | `.indexes canonical_postings` shows `idx_canonical_user_main_rank`; `EXPLAIN QUERY PLAN` on `WHERE user_id='default' ORDER BY fit_score DESC, salary_max_cad DESC LIMIT 10` returns `SEARCH canonical_postings USING INDEX idx_canonical_user_main_rank (user_id=?)` |
| AC3: CHECK constraints reject invalid inserts | PASS | All 14 tests in `test_init_db_m3.py` pass: fit_score=0 rejected, fit_score=6 rejected, citizenship='unknown' rejected, can_hire='maybe' rejected; all valid enum values accepted |
| AC4: Migration is idempotent | PASS | `init_db(db)` called twice on fresh tmp DB: no errors, column set and index set unchanged between first and second call (`test_m3_migration_is_idempotent` passes; independent Python script confirms "Idempotent OK") |
| AC5: DB snapshot taken before migration | PASS | `~/.jd-matcher/snapshots/20260501-0952-pre-m3-001-schema.db` (79 MB) exists with timestamp 2026-05-01 09:52, predating the migration |
| AC6: All ≥979 tests pass post-migration | PASS | 993 passed (baseline 979 + 14 new), 0 failures |

### Live DB integrity checks
| Query | Expected | Actual | Result |
|-------|----------|--------|--------|
| `COUNT(*) FROM canonical_postings` | 257 | 257 | PASS |
| `COUNT(*) FROM postings` | 334 | 334 | PASS |
| `COUNT(*) FROM canonical_postings WHERE fit_score IS NOT NULL` | 0 | 0 | PASS |
| `COUNT(*) FROM canonical_postings WHERE is_filtered = 0` | 257 | 257 | PASS |

### Migration tuple inspection
All 11 `_COLUMN_MIGRATIONS` entries for `canonical_postings` verified against spec:
- `fit_score`: `CHECK (fit_score BETWEEN 1 AND 5)` present — PASS
- `citizenship_requirement`: `CHECK (citizenship_requirement IN ('required', 'preferred', 'not_mentioned'))` present — PASS
- `can_hire_in_canada`: `CHECK (can_hire_in_canada IN ('yes', 'likely', 'no', 'unclear'))` present — PASS
- `industry`: 16-sector CHECK present (all 16 values match `_VALID_INDUSTRIES` in test file) — PASS
- `role_orientation`: No SQL CHECK (Pydantic-layer validation per `top_skills` precedent) — matches spec — PASS
- `is_filtered`: `BOOLEAN NOT NULL DEFAULT 0` — PASS

### Issues found
None. No Minor, Major, or Directional issues identified.
