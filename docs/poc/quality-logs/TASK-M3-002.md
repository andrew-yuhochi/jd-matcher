# Quality Log — TASK-M3-002: C18 v2 Prompt + Pydantic Extension + Cache Key Bump

**Status**: In Progress — pending user approval (Gate 4 probabilistic)
**Date**: 2026-05-01
**Agent**: data-pipeline

---

## Files Modified

| File | Change |
|------|--------|
| `prompts/canonical_extraction_v2.txt` | **New file** — v2 system prompt with 7 new field sections |
| `src/jd_matcher/llm/extract.py` | Pydantic model extended; cache key bumped to 3-tuple; `_build_stricter_prompt` extended for M3 enums; `_write_postings_extracted` adds M3 fields; `_write_postings_failed` no longer writes raw response to `fit_reasoning` |
| `src/jd_matcher/db/init_db.py` | `_COLUMN_MIGRATIONS` entry for `extraction_cache.prompt_version TEXT NOT NULL DEFAULT 'v1'` |
| `src/jd_matcher/db/schema.sql` | `extraction_cache` table updated: `prompt_version` column added, PRIMARY KEY widened to `(text_hash, model_name, prompt_version)` |
| `tests/llm/test_extract_m3.py` | **New file** — 38 tests covering AC #1, #2, #3, #5 |
| `tests/llm/test_extract.py` | Existing tests updated: `_VALID_JSON` and `_SYNTHETIC_JDS` fixtures extended with M3 required fields; `CanonicalExtraction` constructor calls updated with `**_M3_DEFAULTS` |
| `tests/llm/test_validate.py` | `_valid_json()` helper extended with M3 fields; process cache key updated to 3-tuple |

---

## New Prompt File Content Summary

`prompts/canonical_extraction_v2.txt` extends v1 with 7 new field sections:

1. **=== FIT SCORE ===** — 1-5 rubric with explicit per-score definitions + 4 worked examples
2. **=== FIT REASONING ===** — 1-2 sentence instruction citing specific JD content + 2 worked examples
3. **=== INDUSTRY ===** — 16-sector closed taxonomy (verbatim from TDD §C18) + 13 worked examples
4. **=== ROLE ORIENTATION ===** — 3-label taxonomy with definitions + 5 worked examples
5. **=== SALARY (CAD) ===** — USD→CAD conversion (×1.37), spot/range/null rules + 5 worked examples
6. **=== CITIZENSHIP REQUIREMENT ===** — 3-state enum + reason field + 4 worked examples (incl. implicit gates)
7. **=== CAN HIRE IN CANADA ===** — 4-state enum + 6 worked examples

JSON schema at the end includes all 16 fields (7 original M2 + 9 M3).

---

## Pydantic Model Changes

### New enum types added to `extract.py`
- `CanonicalIndustry` — 16-value Literal (verbatim from TDD §C18)
- `CanonicalRoleOrientation` — 3-value Literal: `Engineering | Problem-Solving | Communication`
- `CanonicalCitizenshipRequirement` — 3-value Literal: `required | preferred | not_mentioned`
- `CanonicalCanHireInCanada` — 4-value Literal: `yes | likely | no | unclear`

### New fields on `CanonicalExtraction`
```python
fit_score: int = Field(ge=1, le=5)
fit_reasoning: str
industry: CanonicalIndustry
role_orientation: list[CanonicalRoleOrientation] = Field(min_length=1, max_length=3)
salary_min_cad: int | None = None
salary_max_cad: int | None = None
citizenship_requirement: CanonicalCitizenshipRequirement
citizenship_reason: str
can_hire_in_canada: CanonicalCanHireInCanada
```

All 9 fields are required (no defaults on the enum fields) — missing fields cause `ValidationError` → parse-failure retry.

---

## Cache Key Dimension Change

### Before (M2)
- Module constant: `_PROMPT_PATH = _PROJECT_ROOT / "prompts" / "canonical_extraction_v1.txt"`
- In-process cache: `_PROCESS_CACHE: dict[tuple[str, str], CanonicalExtraction]` keyed by `(text_hash, model_name)`
- DB lookup: `WHERE text_hash = ? AND model_name = ?`
- DB insert: `INSERT OR REPLACE INTO extraction_cache (text_hash, model_name, canonical_extraction_json)`

### After (M3 v2)
- Module constants: `_PROMPT_VERSION = "v2"`, `_PROMPT_PATH = ... / "canonical_extraction_v2.txt"`
- In-process cache: `_PROCESS_CACHE: dict[tuple[str, str, str], CanonicalExtraction]` keyed by `(text_hash, model_name, prompt_version)`
- DB lookup: `WHERE text_hash = ? AND model_name = ? AND prompt_version = ?`
- DB insert: `INSERT OR REPLACE INTO extraction_cache (text_hash, model_name, prompt_version, canonical_extraction_json)`

### Schema migration
Added to `_COLUMN_MIGRATIONS` in `init_db.py`:
```python
("extraction_cache", "prompt_version",
 "ALTER TABLE extraction_cache ADD COLUMN prompt_version TEXT NOT NULL DEFAULT 'v1';")
```

Existing 259 cache entries backfilled to `prompt_version='v1'` by the ALTER TABLE DEFAULT. A v2 lookup (`WHERE prompt_version='v2'`) misses them → LLM re-extraction → v2 `INSERT OR REPLACE` writes the new row (replacing the v1 entry due to the existing PK `(text_hash, model_name)`). Correct behavior: forces re-extraction of the entire 259-posting corpus.

---

## Test Results

**Full suite (SKIP_LIVE=1)**: 1031 passed, 0 failed, 10 skipped

**New test file** `tests/llm/test_extract_m3.py`: **38/38 passed**

Coverage:
- AC #1: 10 tests — prompt file exists, version constant, 7 section headings, JSON schema has all new field names
- AC #2: 18 tests — all enum values accepted, out-of-enum rejected, fit_score bounds 1-5, role_orientation min/max length
- AC #3: 5 tests — 3-tuple process cache key, v1 DB entry misses v2 lookup, v2 DB entry found, provider called on v1 miss, second call uses process cache
- AC #5: 3 tests — 16 sectors count, verbatim match to TDD, match to DB CHECK constraint list
- DB schema: 2 tests — `prompt_version` column present, default='v1' for rows without explicit version

---

## 5-Posting Smoke Test

**Date**: 2026-05-01
**Model**: gpt-4o-mini
**Prompt version**: v2
**Results**: 5/5 successful, 0 parse failures

All 5 postings required live LLM calls (v1 cache entries missed v2 lookup — confirming the load-bearing cache invalidation behavior).

---

### Posting 1 — Clear DS role

**Posting ID**: 102
**Company/Title**: Rockwell Automation / Senior Data Scientist, Agentic AI Products
**JD excerpt**: "Rockwell Automation is a global technology leader focused on helping the world's manufacturers be more productive, sustainable, and agile..."

**v2 JSON output**:
```json
{
  "canonical_title": "Senior Data Scientist, Agentic AI Products",
  "canonical_company": "Rockwell Automation",
  "canonical_seniority": "Senior",
  "canonical_location": "Other",
  "team_or_department": "Data Science & Innovation Organization",
  "top_skills": ["Python", "SQL", "Machine Learning", "Statistical Analysis", "Data Engineering", "Data Analysis", "Causal Inference", "PyTorch", "Feature Engineering", "Predictive Modeling"],
  "role_summary": "The Senior Data Scientist will own the data and modeling layer for agentic AI products, focusing on dataset creation, predictive model development, and statistical rigor. This role involves collaboration with product managers and AI engineers to ensure reliable integration of machine learning tools. The position requires strong foundations in data science and experience in building end-to-end predictive models.",
  "fit_score": 5,
  "fit_reasoning": "The role centers on building predictive models and applying statistical methods, which are core duties of a data scientist. The emphasis on machine learning and data analysis aligns perfectly with the skills of a Vancouver-based Data Scientist.",
  "industry": "Other",
  "role_orientation": ["Engineering", "Problem-Solving"],
  "salary_min_cad": null,
  "salary_max_cad": null,
  "citizenship_requirement": "required",
  "citizenship_reason": "Legal authorization to work in the U.S. is required, and the company will not sponsor individuals for employment visas.",
  "can_hire_in_canada": "unclear"
}
```

**Assessment**:
- `fit_score=5` ✓ — pure DS role with modeling, statistical analysis, ML engineering as core duties
- `industry="Other"` ✓ — Rockwell is industrial automation/manufacturing; no exact taxonomy match, "Other" is correct
- `role_orientation=["Engineering", "Problem-Solving"]` ✓ — builds production models + research/experimentation
- `salary=null/null` ✓ — no salary stated in JD
- `citizenship_requirement=required` ✓ — "Legal authorization to work in the U.S. is required, will not sponsor" detected correctly; the model correctly identified this as a hard gate for an OWP holder
- `can_hire_in_canada=unclear` ✓ — US-based Rockwell, no Canadian presence mentioned for this role; correct uncertainty

---

### Posting 2 — Ambiguous/mixed role

**Posting ID**: 107
**Company/Title**: DarkVision / Data Engineer
**JD excerpt**: "DarkVision is seeking a Data Engineer to join our Imaging & AI team..."

**v2 JSON output**:
```json
{
  "canonical_title": "Data Engineer",
  "canonical_company": "DarkVision",
  "canonical_seniority": "Mid",
  "canonical_location": "Vancouver",
  "team_or_department": "Imaging & AI",
  "top_skills": ["Python", "Data Engineering", "Data Visualization", "AWS", "Statistics", "Signal Processing", "Image Processing", "Automation"],
  "role_summary": "The Data Engineer will develop and optimize data pipelines for reporting and visualization deliverables...",
  "fit_score": 4,
  "fit_reasoning": "The role focuses on data pipeline development and validation, with a strong emphasis on data manipulation and analysis using Python. While there are elements of reporting and visualization, the core responsibilities align closely with data engineering.",
  "industry": "Other",
  "role_orientation": ["Engineering", "Problem-Solving"],
  "salary_min_cad": 96000,
  "salary_max_cad": 150000,
  "citizenship_requirement": "not_mentioned",
  "citizenship_reason": "",
  "can_hire_in_canada": "yes"
}
```

**Assessment**:
- `fit_score=4` — could argue 3 (Data Engineer = adjacent DS with light analytics) or 4 (Imaging & AI team does have modeling work). Score 4 is defensible; may revisit based on user calibration.
- `industry="Other"` ✓ — DarkVision is industrial imaging/NDT tech; no direct taxonomy match
- `salary=96000/150000 CAD` ✓ — correctly parsed from JD (CAD stated explicitly)
- `citizenship_requirement=not_mentioned` ✓ — DarkVision Vancouver company, no citizenship language
- `can_hire_in_canada=yes` ✓ — Vancouver-based company

---

### Posting 3 — Non-DS adjacent

**Posting ID**: 11
**Company/Title**: TELUS / Senior Full Stack Developer (AI/ML/Gen AI Solutions)
**JD excerpt**: "Join the AI Accelerator - Leading Innovation Through Technical Excellence..."

**v2 JSON output**:
```json
{
  "canonical_title": "Senior Full Stack Developer",
  "canonical_company": "TELUS",
  "canonical_seniority": "Senior",
  "canonical_location": "Other",
  "team_or_department": null,
  "top_skills": ["Python", "Machine Learning", "React", "Node.js", "GCP", "Azure", "CI/CD", "RESTful APIs", "Microservices", "Data Engineering"],
  "role_summary": "The Senior Full Stack Developer will lead cross-functional teams to design and implement AI/ML solutions...",
  "fit_score": 4,
  "fit_reasoning": "The role focuses on leading AI/ML solution development and requires strong technical skills in full stack development, particularly with Python and cloud platforms.",
  "industry": "Telecom / Digital Services",
  "role_orientation": ["Engineering", "Problem-Solving", "Communication"],
  "salary_min_cad": null,
  "salary_max_cad": null,
  "citizenship_requirement": "not_mentioned",
  "citizenship_reason": "",
  "can_hire_in_canada": "yes"
}
```

**Assessment**:
- `fit_score=4` — this is the most debatable score. The title is "Senior Full Stack Developer" which could be a 2 or 3 by the rubric (primarily SWE with AI/ML features). However, the role is specifically in the "AI Accelerator" building AI/ML solutions — the AI component is central, not incidental. Score 4 is on the high side; a 3 might also be defensible. **Flag for user review.**
- `industry="Telecom / Digital Services"` ✓ — TELUS is a Canadian telco
- `role_orientation=["Engineering", "Problem-Solving", "Communication"]` ✓ — JD has explicit leadership/stakeholder management + technical + research components
- `can_hire_in_canada=yes` ✓ — TELUS is a Canadian company

---

### Posting 4 — With explicit salary

**Posting ID**: 10
**Company/Title**: Coalition / Applied Scientist II
**JD excerpt**: "Coalition is the world's first Active Insurance provider..."

**v2 JSON output**:
```json
{
  "canonical_title": "Applied Scientist II",
  "canonical_company": "Coalition",
  "canonical_seniority": "Mid",
  "canonical_location": "Remote — Canada",
  "team_or_department": null,
  "top_skills": ["Python", "Machine Learning", "GenAI", "Statistical Analysis", "SQL", "Deep Learning", "A/B Testing", "MLOps", "Data Engineering", "Feature Engineering"],
  "role_summary": "The Applied Scientist II will build and improve machine learning and GenAI models for underwriting decisions...",
  "fit_score": 5,
  "fit_reasoning": "The role focuses heavily on developing and deploying ML models, with core duties in statistical analysis and experimentation, making it a pure data science role.",
  "industry": "Insurance / Insurtech",
  "role_orientation": ["Engineering", "Problem-Solving"],
  "salary_min_cad": 115300,
  "salary_max_cad": 144100,
  "citizenship_requirement": "not_mentioned",
  "citizenship_reason": "",
  "can_hire_in_canada": "yes"
}
```

**Assessment**:
- `fit_score=5` ✓ — pure Applied Scientist role (ML + statistics + GenAI)
- `industry="Insurance / Insurtech"` ✓ — Coalition is a cyber insurance company
- `salary=115300/144100 CAD` ✓ — USD range correctly converted (stated as $84k-$105k USD × 1.37 ≈ $115k-$144k CAD)
- `can_hire_in_canada=yes` ✓ — "Remote — Canada" explicitly in the JD
- `citizenship_requirement=not_mentioned` ✓ — Coalition is a US company but hires in Canada; no citizenship language

---

### Posting 5 — Potential citizenship requirement

**Posting ID**: 114
**Company/Title**: CIBC / Investment Research Analyst
**JD excerpt**: "We're building a relationship-oriented bank for the modern world..."

**v2 JSON output**:
```json
{
  "canonical_title": "Investment Research Analyst",
  "canonical_company": "CIBC",
  "canonical_seniority": "Mid",
  "canonical_location": "Toronto",
  "team_or_department": "Multi-Asset and Currency Research",
  "top_skills": ["Python", "PowerBI", "Eviews", "Macroeconomic Analysis", "Investment Research", "Forecasting Planning", "Risk Assessments", "Financial Markets Research", "Portfolio Management", "Market Research"],
  "role_summary": "The Investment Research Analyst will deliver high-quality investment research to influence portfolio decisions...",
  "fit_score": 4,
  "fit_reasoning": "The role focuses on macroeconomic analysis and investment research, which aligns well with data science and ML skills, particularly in modeling and analysis.",
  "industry": "Financial Services / Asset Management",
  "role_orientation": ["Problem-Solving", "Communication"],
  "salary_min_cad": 126000,
  "salary_max_cad": 174000,
  "citizenship_requirement": "not_mentioned",
  "citizenship_reason": "",
  "can_hire_in_canada": "yes"
}
```

**Assessment**:
- `fit_score=4` — macroeconomic/investment research with Python and quantitative modeling. Not pure DS but analytically adjacent. Score 4 is defensible.
- `industry="Financial Services / Asset Management"` ✓ — CIBC is a Canadian bank
- `salary=126000/174000 CAD` ✓ — extracted correctly from the JD
- `citizenship_requirement=not_mentioned` ✓ — CIBC does hire OWP holders; no explicit citizenship language in this JD
- `can_hire_in_canada=yes` ✓ — Canadian company

---

## Cost Summary

| Posting | Company | Posting ID | Input tokens | Output tokens | Cost (USD) |
|---------|---------|------------|-------------|--------------|------------|
| 1 (Clear DS) | Rockwell Automation | 102 | 5,585 | 328 | $0.001035 |
| 2 (Mixed) | DarkVision | 107 | 5,590 | 272 | $0.001002 |
| 3 (Non-DS) | TELUS | 11 | 5,428 | 317 | $0.001004 |
| 4 (Salary) | Coalition | 10 | 6,386 | 298 | $0.001137 |
| 5 (Citizenship) | CIBC | 114 | 5,762 | 298 | $0.001043 |
| **Total** | | | **28,751** | **1,513** | **$0.005221** |

Note: v2 prompt is ~500 tokens longer than v1 (the 7 new sections). This is reflected in the higher input token counts (~5.5k vs ~3.5k in M2).

---

## DB Snapshot

Pre-migration snapshot: `~/.jd-matcher/snapshots/20260501-1029-pre-m3-002-prompt.db`

Migration ran: `prompt_version` column added to `extraction_cache` with 259 rows backfilled to `'v1'`.

---

## Items for User Review (Gate 4)

The following smoke-test assessments are **probabilistic** and require user approval before AC #4 is marked Done:

1. **Rockwell Automation (posting 102)**: `citizenship_requirement=required` — is this correct? The JD says "Legal authorization to work in the U.S. is required" — this IS a hard gate for an OWP Canada holder applying to a US role.

2. **TELUS (posting 11)**: `fit_score=4` — the title is "Senior Full Stack Developer" but the role is in an "AI Accelerator" building AI/ML solutions. Is 4 (primarily DS-adjacent) appropriate, or should it be 3 (mixed, SWE primary)?

3. **DarkVision (posting 107)**: `fit_score=4` — Data Engineer with imaging/AI team context. Is 4 appropriate, or 3?

4. **General**: `industry="Other"` for Rockwell Automation and DarkVision. Both are niche tech companies not in the 16-sector list — is "Other" acceptable for these, or should a different sector be chosen?
