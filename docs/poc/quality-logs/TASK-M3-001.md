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
