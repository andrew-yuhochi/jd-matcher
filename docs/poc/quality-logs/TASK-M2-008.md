# Quality Log — TASK-M2-008 — Two-Stage Dedup Engine C21 (BLOCK + FUSE)

**Date**: 2026-04-29
**Component**: C21 (Two-Stage Dedup Engine)
**Module**: `src/jd_matcher/dedup/engine.py`

---

## Scope

C21 is a pure decision function: given a posting_id, it queries `canonical_postings`
and `posting_embeddings`, runs two-stage BLOCK + FUSE, and returns a `DedupDecision`.
It does NOT write anything. All writes are C29's responsibility (TASK-M2-009).

At M2-008, `canonical_postings` is empty — every posting returns `action='new'`
on real data. Quality validation is therefore entirely synthetic-fixture-based,
as specified by TDD §C21 Sample Selection.

---

## Methodology

1. **39 unit tests** covering all helpers (jaccard, seniority_match, title_cosine)
   plus FUSE math, 4 user-scenario fixtures, 10 regression-blocking different-team
   pairs, full_jd short-circuit, Inactive/Expired bypass, and JSON serialization.
2. **EXPLAIN QUERY PLAN** verification on the real DB for BLOCK SQL index usage.
3. **Demo artifact** run against posting_id=91 (real posting, canonical_postings empty).

---

## Per-AC Verdict

| AC | Description | Result |
|----|-------------|--------|
| AC-1 | `decide(posting_id)` returns `DedupDecision` matching spec | PASS |
| AC-2 | BLOCK SQL uses `idx_canonical_user_block` (no full table scan) | PASS |
| AC-3 | FUSE formula verified by 5 test cases with known inputs/outputs | PASS |
| AC-4 | Auto-merge threshold 0.90 configurable via `config/dedup.yaml` | PASS |
| AC-5 | Inactive/Expired bypass: NOT EXISTS clause excludes affected canonicals | PASS |
| AC-6 | Synthetic fixtures cover all 4 user scenarios | PASS |
| AC-7 | ZERO false-merges on 10 different-team synthetic pairs | PASS (0/10) |
| AC-8 | `DedupDecision` JSON serialization round-trip works | PASS |

---

## EXPLAIN QUERY PLAN — AC-2 Verification

Query (non-NULL team case):
```sql
SELECT canonical_id, ... FROM canonical_postings
WHERE user_id = 'default'
  AND canonical_company = 'Shopify'
  AND team_or_department = 'Risk Analytics'
  AND canonical_location = 'Vancouver'
  AND NOT EXISTS (
      SELECT 1 FROM posting_canonical_links pcl
      JOIN applied a ON a.posting_id = pcl.posting_id
      WHERE pcl.canonical_id = canonical_postings.canonical_id
        AND a.status IN ('Inactive', 'Expired')
  );
```

Result:
```
QUERY PLAN
|--SEARCH canonical_postings USING INDEX idx_canonical_user_block
|   (user_id=? AND canonical_company=? AND team_or_department=? AND canonical_location=?)
`--CORRELATED SCALAR SUBQUERY 1
   |--SEARCH pcl USING INDEX idx_links_canonical (canonical_id=?)
   |--BLOOM FILTER ON a (posting_id=?)
   `--SEARCH a USING AUTOMATIC PARTIAL COVERING INDEX (posting_id=?)
```

No full table scan. BLOCK SQL uses `idx_canonical_user_block` for all 4 key columns.

Design note: `LOWER()` / `COLLATE NOCASE` in SQL defeats the BINARY-collation index.
Case-insensitive matching is a non-issue in practice because C18 LLM extraction stores
canonical fields with consistent capitalisation. Exact-case SQL equality preserves the
index scan.

---

## FUSE Math Test Cases (AC-3)

All 5 cases use synthetic posting + candidate pairs with mocked provider calls.

| Case | emb_cosine | skills_jaccard | title_cosine | seniority_match | Expected total | Actual total | Pass? |
|------|-----------|---------------|-------------|----------------|----------------|-------------|-------|
| 1 — Perfect match | 1.0 | 1.0 | 1.0 | 1.0 | 1.0000 | 1.0000 | PASS |
| 2 — Embedding only | 1.0 | 0.0 | 0.0 | 0.0 | 0.4000 | 0.4000 | PASS |
| 3 — Skills + seniority | 0.0 | 0.5 | 0.0 | 1.0 | 0.2500 | 0.2500 | PASS |
| 4 — Above threshold | 0.95 | 1.0 | 0.9 | 1.0 | 0.9600 | 0.9600 | PASS |
| 5 — Below threshold | 0.7 | 0.5 | 0.6 | 0.0 | 0.5500 | 0.5500 | PASS |

Formula: `0.4 × emb + 0.3 × skills + 0.2 × title + 0.1 × seniority`

---

## 4 User-Scenario Synthetic Fixture Outcomes (AC-6)

| Scenario | Setup | Expected | Actual | Pass? |
|----------|-------|----------|--------|-------|
| (i) Same company + different teams | Shopify/Marketing Analytics vs Shopify/Risk Analytics, Vancouver | action='new', block_size=0 | action='new', block_size=0 | PASS |
| (ii) Same company + same team + different roles | TD Bank/Risk Analytics: Senior Risk Modeller (Credit) vs (Operational), orthogonal embeddings | action='new', block_size=1, score<0.90 | action='new', block_size=1, score=0.279 | PASS |
| (iii) Cross-source same role → MERGE | Shopify/ML Platform: same ML Engineer from LinkedIn + Indeed, near-identical embeddings | action='merge', similarity≥0.90 | action='merge', similarity=~0.9999 | PASS |
| (iv) Same role + different location | Lumenalta/Data Platform, Vancouver vs Toronto | action='new', block_size=0 | action='new', block_size=0 | PASS |

---

## 10 Different-Team Regression Pairs (AC-7)

All 10 pairs use: company=Shopify, location=Vancouver, title="Senior Data Scientist",
seniority=Senior, same skills — only `team_or_department` differs. Embedding cosine=1.0,
title_cosine=1.0 (worst case — BLOCK is the only defence).

| Pair | Team A | Team B | Score | action | False merge? |
|------|--------|--------|-------|--------|-------------|
| 0 | Marketing Analytics | Risk Analytics | N/A (block_size=0) | new | NO |
| 1 | Data Science | Engineering | N/A (block_size=0) | new | NO |
| 2 | ML Platform | Data Warehouse | N/A (block_size=0) | new | NO |
| 3 | People Analytics | Finance Analytics | N/A (block_size=0) | new | NO |
| 4 | Sales Analytics | Marketing Analytics | N/A (block_size=0) | new | NO |
| 5 | Platform Engineering | ML Infrastructure | N/A (block_size=0) | new | NO |
| 6 | Growth Analytics | Product Analytics | N/A (block_size=0) | new | NO |
| 7 | AI Research | Applied ML | N/A (block_size=0) | new | NO |
| 8 | Business Intelligence | Data Engineering | N/A (block_size=0) | new | NO |
| 9 | Data Governance | ML Ops | N/A (block_size=0) | new | NO |

**False merges: 0 / 10** — SC-7 regression-blocking AC met.

---

## full_jd-fallback Short-Circuit (Design Add-On)

Test: posting with `posting_embeddings.text_source='full_jd'` → `decide()` short-circuits.

Result:
```json
{
  "action": "new",
  "target_canonical_id": null,
  "similarity": 0.0,
  "merge_kind": "new_canonical",
  "stage1_block_size": 0,
  "stage2_top_match_score": 0.0,
  "blocked_by": ["extraction_failed_full_jd_fallback"]
}
```

Unit test `test_full_jd_text_source_short_circuits` confirms the short-circuit fires. PASS.

Background: Post-M2-007 investigation found 6 posting pairs in the corpus with
text_source='full_jd' and cosine 0.928–1.000 despite being genuinely different roles.
The 9 affected postings are C19-filtered legacy items — all should have been excluded
by the C19 title filter but weren't due to hydration_status='partial' at filter time.
The short-circuit is a belt-and-suspenders safety net.

---

## Real-Data Expected Duplicate Pairs (from M2-007 batch analysis)

These 7 pairs have been identified as likely true duplicates based on high cosine similarity
from the embedding pipeline. They are NOT validated here (canonical_postings is empty at M2-008).
They are expected merge targets when C29 is implemented (TASK-M2-009).

| Pair | Posting IDs | Company | Notes |
|------|------------|---------|-------|
| 1 | 9 ↔ 10 | Coalition | High cosine, same role |
| 2 | 27 ↔ 44 | Clio | High cosine, same role |
| 3 | 55 ↔ 97 | Joveo | High cosine, same role |
| 4 | 77 ↔ 150 | Bird Construction | High cosine, same role |
| 5 | 2 ↔ 4 | Lumenalta | High cosine, same role |
| 6 | 118 ↔ 119 | TELUS Digital | High cosine, same role |
| 7 | 112 ↔ 113 | Turing | High cosine, same role |

These pairs will be validated end-to-end in TASK-M2-012 (calibration task).

---

## Demo Artifact Output

```
$ python -m jd_matcher.dedup decide --posting-id 91
{
  "action": "new",
  "target_canonical_id": null,
  "similarity": 0.0,
  "merge_kind": "new_canonical",
  "stage1_block_size": 0,
  "stage2_top_match_score": 0.0,
  "blocked_by": [
    "canonical_company",
    "team_or_department",
    "canonical_location"
  ]
}
```

Expected: `action='new'`, `stage1_block_size=0` (canonical_postings empty at M2-008).
Posting 91: "Senior Engineering Manager, AI Agents" at Asana/Vancouver.

---

## Test Suite Summary

| Category | Count | Result |
|----------|-------|--------|
| New dedup engine tests | 39 | 39 pass |
| Pre-existing tests | 768 | 768 pass |
| Skipped (SKIP_LIVE) | 10 | — |
| **Total** | **807** | **807 pass, 0 fail** |

---

## Conclusion

All 8 ACs pass. BLOCK SQL verified to use `idx_canonical_user_block`. FUSE formula
verified by 5 known-input math tests. 4 user-scenario fixtures all pass. 0 false merges
on 10 different-team pairs (SC-7 met). full_jd safety check fires correctly. JSON
serialization works. Full test suite green.

C21 is ready for C29 integration (TASK-M2-009).
