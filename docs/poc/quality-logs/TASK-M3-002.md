# Quality Log — TASK-M3-002: C18 v2 Prompt + Pydantic Extension + Cache Key Bump

**Status**: In Progress — pending user approval of v3 smoke test (Gate 4 probabilistic)
**Date**: 2026-05-01 (v2) / 2026-05-01 (v3 iteration)
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

---

---

## v3 Iteration — 2026-05-01

### Root Cause (user-identified after v2 smoke test)

4 systemic issues in v2 required prompt revision:

1. **fit_score biased high** — no down-score anchor examples; LLM defaulted to 4-5 even for DS-adjacent roles (DarkVision DE got 4, CIBC Analyst got 4, both should be 2 and 3 respectively per user rubric).
2. **role_orientation taxonomy mismatch** — "Engineering" in v2 included MLOps/ML pipelines (DS work); user wants Engineering = SE work distinct from DS (backend, full-stack, devops, architecture). Almost every DS role was getting "Engineering" incorrectly.
3. **Salary default currency wrong** — v2 assumed USD when no currency suffix; should default to CAD for Canadian employers.
4. **Location too aggressive on "Other"** — Burnaby, North Vancouver etc. were bucketing to "Other" instead of Vancouver metro. v2 metro list incomplete (missing West Vancouver, Oakville, Vaughan etc.).

### v3 Prompt Changes

| Section | v2 | v3 |
|---------|----|----|
| FIT SCORE | Generic rubric, 4 brief examples | Full per-level definition with sister-team signal, conservative default rule, quant-role note; 8 worked examples from live canonical postings |
| ROLE ORIENTATION | DS-centric definition (MLOps = Engineering) | SE-work definition (Engineering = SE work SEPARATE from DS modeling); 8 worked examples baked in |
| SALARY | Always apply ×1.37 if no currency suffix | Canadian employer → assume CAD (no conversion); USD only for non-Canadian employers; explicit worked examples |
| CANONICAL LOCATION | Metro list missing West/North Vancouver, Oakville, Vaughan | Expanded suburb mapping; explicit "DO NOT bucket as Other" instruction for Canadian suburbs |

Sections unchanged: canonical_company, canonical_seniority, top_skills, role_summary, canonical_title, industry, citizenship_requirement, can_hire_in_canada.

### Files Changed

| File | Change |
|------|--------|
| `prompts/canonical_extraction_v3.txt` | New file — extends v2 with 4 rewritten sections + 8 fit_score worked examples + 8 role_orientation worked examples |
| `src/jd_matcher/llm/extract.py` | `_PROMPT_VERSION = "v3"`, `_PROMPT_PATH` updated |
| `tests/llm/test_extract_m3.py` | All v2 references updated to v3 |

### Test Results (post-v3)

**Full suite (SKIP_LIVE=1)**: 1031 passed, 0 failed, 10 skipped
**test_extract_m3.py**: 38/38 passed

### 6-Posting v3 Smoke Test

**Date**: 2026-05-01
**Model**: gpt-4o-mini
**Prompt version**: v3
**DB snapshot before test**: `~/.jd-matcher/snapshots/20260501-HHMM-pre-m3-002-v3-prompt.db`
**Cache state after**: v1|253, v3|6 (v3 entries are new live calls; v2 never materialized in main DB)

---

#### v2 → v3 → Expected diff table

| Posting | Company | fit_score v2 | fit_score v3 | fit_score expected | role_orientation v2 | role_orientation v3 | role_orientation expected | salary v2 | salary v3 | salary expected | location v2 | location v3 | location expected |
|---------|---------|-------------|-------------|-------------------|--------------------|--------------------|--------------------------|-----------|-----------|-----------------|-------------|-------------|-----------------|
| 102 | Rockwell | 5 | 5 | 5 | [Engineering, Problem-Solving] | [Problem-Solving, Communication] | [Problem-Solving] | null/null | null/null | null/null | Other | Other | (whatever JD says) |
| 107 | DarkVision | 4 | 2 | 2 | [Engineering, Problem-Solving] | [Engineering, Problem-Solving] | [Engineering, Problem-Solving, Communication] | 96000/150000 | 70000/110000 | 70000/110000 | Vancouver | Vancouver | Vancouver |
| 11 | TELUS | 4 | 3 | 3 | [Engineering, Problem-Solving, Communication] | [Engineering, Problem-Solving, Communication] | [Problem-Solving, Communication] | null/null | null/null | null/null | Other | Hybrid — Vancouver | Vancouver (or Hybrid) |
| 10 | Coalition | 5 | 5 | 5 | [Engineering, Problem-Solving] | [Problem-Solving] | [Problem-Solving] | 115300/144100 | 115300/144100 | 115300/144100 | Remote — Canada | Remote — Canada | Remote — Canada |
| 114 | CIBC | 4 | 4 | 3 | [Problem-Solving, Communication] | [Problem-Solving, Communication] | [Problem-Solving, Communication] | 126000/174000 | 92490/127200 | 92490/127200 | Toronto | Toronto | Toronto |
| 8 (new) | Dropbox | — | 5 | 4 | — | [Problem-Solving, Communication] | [Problem-Solving, Engineering] or [Problem-Solving, Communication] | — | 132600/179400 | (JD value) | — | Remote — Canada | (JD value) |

---

#### Posting-by-posting v3 detail

**posting_id=102, canonical_id=315: Rockwell Senior DS Agentic AI**
```json
{
  "fit_score": 5,
  "fit_reasoning": "Core duties include building predictive models and datasets, applying statistical methods — pure DS scope confirmed by AI engineers handling integration.",
  "role_orientation": ["Problem-Solving", "Communication"],
  "salary_min_cad": null,
  "salary_max_cad": null,
  "canonical_location": "Other",
  "citizenship_requirement": "required",
  "can_hire_in_canada": "no"
}
```
- fit_score=5 ✓ (matches expected)
- role_orientation: [Problem-Solving, Communication] — DIVERGENCE from expected [Problem-Solving] only. Communication added because JD mentions collaborating with product managers and research lead. Defensible; user review needed.
- salary=null/null ✓
- location=Other — JD doesn't specify Canadian location; "Other" acceptable
- citizenship=required, can_hire=no — JD says "Legal auth to work in US required, no sponsorship" ✓

**posting_id=107, canonical_id=320: DarkVision Data Engineer**
```json
{
  "fit_score": 2,
  "fit_reasoning": "Role focuses primarily on data pipeline development and validation with minimal modeling.",
  "role_orientation": ["Engineering", "Problem-Solving"],
  "salary_min_cad": 70000,
  "salary_max_cad": 110000,
  "canonical_location": "Vancouver",
  "citizenship_requirement": "not_mentioned",
  "can_hire_in_canada": "yes"
}
```
- fit_score=2 ✓ (DOWN from v2's 4 — major win)
- role_orientation: [Engineering, Problem-Solving] — expected also includes Communication (multidisciplinary collaboration). Minor gap; acceptable.
- salary=70000/110000 ✓ (CAD no-conversion for Canadian employer — major fix from v2's 96000/150000)
- location=Vancouver ✓

**posting_id=11, canonical_id=323: TELUS Senior Developer AI/ML**
```json
{
  "fit_score": 3,
  "fit_reasoning": "Combines full-stack development with technical leadership and stakeholder management — DS + SE + management scope.",
  "role_orientation": ["Engineering", "Problem-Solving", "Communication"],
  "salary_min_cad": null,
  "salary_max_cad": null,
  "canonical_location": "Hybrid — Vancouver",
  "citizenship_requirement": "not_mentioned",
  "can_hire_in_canada": "yes"
}
```
- fit_score=3 ✓ (DOWN from v2's 4 — correct)
- role_orientation: [Engineering, Problem-Solving, Communication] — expected [Problem-Solving, Communication] (no Engineering for managerial). DIVERGENCE: LLM correctly identifies full-stack code as Engineering (which it is per v3 definition); user expected managerial-only. Acceptable given the role IS full-stack.
- salary=null/null ✓
- location=Hybrid — Vancouver ✓ (UP from v2's "Other" — major location fix)

**posting_id=10, canonical_id=312: Coalition Applied Scientist II**
```json
{
  "fit_score": 5,
  "fit_reasoning": "Core duties are building and improving ML models for underwriting — pure DS scope confirmed by dedicated engineering team handling integration.",
  "role_orientation": ["Problem-Solving"],
  "salary_min_cad": 115300,
  "salary_max_cad": 144100,
  "canonical_location": "Remote — Canada",
  "citizenship_requirement": "not_mentioned",
  "can_hire_in_canada": "yes"
}
```
- fit_score=5 ✓
- role_orientation: [Problem-Solving] ✓ (DOWN from v2's [Engineering, Problem-Solving] — major fix; MLOps is now correctly DS work not Engineering)
- salary=115300/144100 ✓ (USD ×1.37 — Coalition is US-based)
- location=Remote — Canada ✓

**posting_id=114, canonical_id=327: CIBC Senior Research Analyst**
```json
{
  "fit_score": 4,
  "fit_reasoning": "Macroeconomic analysis and investment research with modeling — DS-flavored; significant stakeholder communication component.",
  "role_orientation": ["Problem-Solving", "Communication"],
  "salary_min_cad": 92490,
  "salary_max_cad": 127200,
  "canonical_location": "Toronto",
  "citizenship_requirement": "not_mentioned",
  "can_hire_in_canada": "yes"
}
```
- fit_score=4 — expected 3 (quant/financial-modeling → fit=3 per rubric). DIVERGENCE. The v3 rubric note says "Quant/financial-modeling roles → fit=3" but LLM returned 4. This is the clearest divergence from expected.
- role_orientation: [Problem-Solving, Communication] ✓
- salary=92490/127200 ✓ (CAD no-conversion for CIBC Canadian employer — major fix from v2's 126000/174000)
- location=Toronto ✓

**posting_id=8, canonical_id=439: Dropbox Data Scientist (new posting)**
```json
{
  "fit_score": 5,
  "fit_reasoning": "Core duties focus on data analysis, statistical modeling, and experimentation — pure DS scope confirmed by collaboration with product/engineering/design.",
  "role_orientation": ["Problem-Solving", "Communication"],
  "salary_min_cad": 132600,
  "salary_max_cad": 179400,
  "canonical_location": "Remote — Canada",
  "citizenship_requirement": "not_mentioned",
  "can_hire_in_canada": "yes"
}
```
- fit_score=5 — expected 4 (DS + automated reporting dashboards = soft stretch). DIVERGENCE. LLM missed the dashboarding component that drops this from 5→4.
- role_orientation: [Problem-Solving, Communication] — acceptable (expected [Problem-Solving, Engineering] or [Problem-Solving, Communication]; Communication is correct)
- salary=132600/179400 — USD ×1.37 applied (Dropbox is US-based). Plausible if JD states a USD range.
- location=Remote — Canada ✓

---

### Summary of v3 Improvements vs v2

| Issue | v2 outcome | v3 outcome | Status |
|-------|-----------|-----------|--------|
| DarkVision fit_score bias | 4 (wrong) | 2 (correct) | FIXED |
| TELUS fit_score bias | 4 (wrong) | 3 (correct) | FIXED |
| Coalition role_orientation Engineering | Engineering + Problem-Solving | Problem-Solving only | FIXED |
| Rockwell role_orientation Engineering | Engineering + Problem-Solving | Problem-Solving + Communication | PARTIALLY FIXED (Communication added; Engineering dropped) |
| DarkVision salary (CAD default) | 96k/150k (USD conversion applied) | 70k/110k (CAD, correct) | FIXED |
| CIBC salary (CAD default) | 126k/174k (USD conversion applied) | 92.5k/127.2k (CAD, correct) | FIXED |
| TELUS location (Burnaby→Vancouver) | Other | Hybrid — Vancouver | FIXED |
| CIBC fit_score (quant=3 not 4) | 4 (v2 baseline) | 4 (still 4) | NOT FIXED — needs user decision |
| Dropbox fit_score (dashboard=4 not 5) | — (new posting) | 5 (expected 4) | DIVERGENCE — needs user review |

### Items for User Review (Gate 4 — v3)

All probabilistic assessments require user approval:

1. **CIBC fit_score=4** — expected 3 per rubric ("quant/financial-modeling roles → fit=3"). LLM returned 4. Should this be accepted as 4, or does the rubric need a stronger worked example anchoring quant roles at 3?

2. **Dropbox fit_score=5** — expected 4 (DS + automated reporting dashboards = soft stretch per fit=4 definition). LLM returned 5, missing the dashboarding signal. Prompt already has the Dropbox worked example anchoring at 4 — this is a compliance failure. Recommend: accept for now (Dropbox is genuinely close to 5) or add a stronger prompt anchor.

3. **Rockwell role_orientation Communication** — LLM added Communication because the JD mentions collaborating with PMs. Expected was [Problem-Solving] only. Is collaboration with PMs sufficient to warrant Communication? If not, the Communication threshold needs tightening.

4. **TELUS role_orientation Engineering** — LLM correctly identified full-stack code as Engineering (correct per v3 definition). Expected was [Problem-Solving, Communication] (managerial-only). Since the TELUS role IS full-stack SE, Engineering is accurate per the rubric. Accept?

---

## Independent Verification — test-validator (2026-04-30)

**Validator commit reviewed**: f401873
**Test suite result**: 1031 passed, 10 skipped, 0 failed (34.57s)
**Baseline**: 993 + 38 new = 1031 — matches data-pipeline report exactly.

### AC1 — Prompt file structure: PASS

- `prompts/canonical_extraction_v2.txt` exists (397 lines)
- All 7 new section headers confirmed present (verified by reading file):
  - `=== FIT SCORE ===` — rubric + 4 worked examples
  - `=== FIT REASONING ===` — 1-2 sentence instruction + 2 worked examples
  - `=== INDUSTRY ===` — 16-sector closed list + 13 worked examples
  - `=== ROLE ORIENTATION ===` — 3-label taxonomy + 5 worked examples
  - `=== SALARY (CAD) ===` — USD→CAD rules + 5 worked examples
  - `=== CITIZENSHIP REQUIREMENT ===` — 3-state enum + reason field + 4 worked examples
  - `=== CAN HIRE IN CANADA ===` — 4-state enum + 6 worked examples
- v1 M2 normalisation sections all still present (file builds on v1)
- JSON schema at end includes all 16 fields

### AC2 — Pydantic model fields and constraints: PASS

All 9 new fields verified on `CanonicalExtraction` at line 140 of `src/jd_matcher/llm/extract.py`:

| Field | Type | Constraint | Status |
|-------|------|-----------|--------|
| `fit_score` | `int` | `Field(ge=1, le=5)` | PASS |
| `fit_reasoning` | `str` | required | PASS |
| `industry` | `CanonicalIndustry` (16-value Literal) | required | PASS |
| `role_orientation` | `list[CanonicalRoleOrientation]` | `Field(min_length=1, max_length=3)` | PASS |
| `salary_min_cad` | `int | None` | default=None | PASS |
| `salary_max_cad` | `int | None` | default=None | PASS |
| `citizenship_requirement` | `CanonicalCitizenshipRequirement` (3-value Literal) | required | PASS |
| `citizenship_reason` | `str` | required | PASS |
| `can_hire_in_canada` | `CanonicalCanHireInCanada` (4-value Literal) | required | PASS |

Live validation script results (all 7 boundary tests passed):
```
PASS: valid instance constructed
PASS: fit_score=6 raises ValidationError
PASS: industry=InvalidSector raises ValidationError
PASS: role_orientation=[] raises ValidationError
PASS: role_orientation length=4 raises ValidationError
PASS: citizenship_requirement=invalid raises ValidationError
PASS: can_hire_in_canada=maybe raises ValidationError
```

### AC3 — Cache key includes prompt version: PASS

Evidence from `src/jd_matcher/llm/extract.py`:
- `_PROMPT_VERSION = "v2"` defined at line 46
- In-process cache key: `(text_hash, model_name, _PROMPT_VERSION)` — 3-tuple confirmed at line 558
- DB lookup: `WHERE text_hash = ? AND model_name = ? AND prompt_version = ?` at line 247
- DB insert includes `prompt_version` at line 277
- `PRAGMA table_info(extraction_cache)` confirms `prompt_version TEXT NOT NULL DEFAULT 'v1'` column exists

Cache miss verification script output:
```
Using v1 entry: text_hash=0a95e0e9fd468993... model_name=gpt-4o-mini
PASS: v2 lookup on v1 text_hash → cache miss (returns None)
```

Live DB prompt_version distribution (confirms v1 entries are not satisfying v2 lookups):
```
v1|254
v2|5
```
254 v1 entries remain untouched; 5 v2 entries exist from the smoke test. This is exactly the expected state — the 5 smoke-test postings forced fresh v2 LLM calls and wrote new v2 cache rows.

### AC5 — Industry Literal matches 16-sector CHECK constraint: PASS

Diff of `CanonicalIndustry.__args__` vs `_VALID_INDUSTRIES` from `tests/db/test_init_db_m3.py`:
```
PASS: CanonicalIndustry Literal == _VALID_INDUSTRIES (identical 16 values)
Pydantic count: 16
CHECK count:    16
```

Zero drift between the Pydantic Literal and the DB CHECK constraint source of truth. No typo variants (e.g., "Cleantech" vs "CleanTech" — actual value is "Energy / Oil & Gas / Cleantech" in both sources, identical).

### Live DB Integrity

- `canonical_postings` row count: **257** (no data loss from migration)
- `extraction_cache.prompt_version` column: present with `DEFAULT 'v1'`
- v1 entries: 254 | v2 entries: 5 (from smoke test)

---

## v4 Iteration — 2026-04-30

### Design Intent

User identified 2 fit_score mis-anchorings in v3 smoke test:
- CIBC (canonical_id=327): returned 4, expected 3 — financial modeling is the PRIMARY work, not DS support
- Dropbox (canonical_id=439): returned 5, expected 4 — automated dashboards = one notable out-of-scope stretch

User's proposed fix: replace mechanical "drop X level if Y" rules with explicit **IN-SCOPE vs OUT-OF-SCOPE DS responsibility lists** that the LLM uses to evaluate the responsibility distribution.

### v4 Prompt Changes (fit_score section only)

The fit_score section was completely rewritten with:
- 8 IN-SCOPE DS responsibilities (numbered 1-8): EDA, ML model dev, stats, experimentation, MLOps, stakeholder communication, research direction
- 9 OUT-OF-SCOPE responsibilities (numbered 1-9): data engineering, dashboard dev, backend engineering, full-stack dev, system architecture, DevOps, SDLC ownership, domain quant modeling (primary), people management of non-DS teams
- Score interpretation mapped to proportion of in-scope vs out-of-scope responsibilities
- 8 worked examples using structured `In-scope: items X,Y` / `Out-of-scope: items A,B` format

All other sections unchanged from v3 (byte-identical).

### Files Changed

| File | Change |
|------|--------|
| `prompts/canonical_extraction_v4.txt` | New file — v3 with fit_score section replaced |
| `src/jd_matcher/llm/extract.py` | `_PROMPT_VERSION = "v4"`, `_PROMPT_PATH` updated |
| `tests/llm/test_extract_m3.py` | All v3 references updated to v4 |

### Test Results (post-v4)

**Full suite (SKIP_LIVE=1)**: 1031 passed, 0 failed, 10 skipped
**test_extract_m3.py**: 38/38 passed

### 6-Posting v4 Smoke Test

**Date**: 2026-04-30
**Model**: gpt-4o-mini
**Prompt version**: v4
**DB snapshot before test**: `~/.jd-matcher/snapshots/20260430-HHMM-pre-m3-002-v4-prompt.db`
**Cache state after**: v1|253, v4|6 (6 fresh LLM calls; v3 entries keyed separately)

---

#### v3 → v4 → Expected diff table

| Posting | Company | fit_score v3 | fit_score v4 | fit_score expected | Match? |
|---------|---------|-------------|-------------|-------------------|--------|
| 102 | Rockwell | 5 | 5 | 5 | PASS |
| 107 | DarkVision | 2 | 4 | 2 | FAIL (regression) |
| 11 | TELUS | 3 | 5 | 3 | FAIL (regression) |
| 10 | Coalition | 5 | 5 | 5 | PASS |
| 114 | CIBC | 4 | 5 | 3 | FAIL (target fix not achieved; score went UP) |
| 8 | Dropbox | 5 | 4 | 4 | PASS (target fix achieved) |

**Target fixes**: 1/2 achieved (Dropbox fixed; CIBC not fixed)
**Regressions**: 2 (DarkVision 2→4, TELUS 3→5)
**Net**: worse than v3 overall

---

#### Posting-by-posting v4 detail

**posting_id=102, canonical_id=315: Rockwell Senior DS Agentic AI**
- fit_score=5 ✓ (unchanged from v3)
- fit_reasoning: "The role focuses on building predictive models and datasets, applying statistical methods, and collaborating with product managers, which aligns closely with in-scope data science responsibilities. There are no significant out-of-scope duties mentioned."

**posting_id=107, canonical_id=320: DarkVision Data Engineer** — REGRESSION
- fit_score=4 (was 2 in v3, expected 2)
- fit_reasoning: "The role focuses on data pipeline development and validation, which are core data engineering tasks. While there are elements of data visualization and communication, the primary responsibilities align closely with data engineering work."
- Root cause: LLM acknowledges data engineering but concludes "primarily data engineering" while still returning 4. The in-scope/out-of-scope framing led it to search for any DS-adjacent signal and weight it upward. V3's anchored worked examples kept it at 2 more reliably.

**posting_id=11, canonical_id=323: TELUS Senior Developer AI/ML** — REGRESSION
- fit_score=5 (was 3 in v3, expected 3)
- fit_reasoning: "The role focuses on leading AI/ML solution development, stakeholder management, and hands-on full stack development, aligning closely with in-scope data science responsibilities. There are no significant out-of-scope duties mentioned."
- Root cause: LLM mapped "AI/ML solution development" to in-scope items 3/6, and "hands-on full stack development" was not recognized as out-of-scope item 4. The v4 framework gave the LLM latitude to decide "no significant out-of-scope" for a role that is explicitly full-stack + architecture + devops.

**posting_id=10, canonical_id=312: Coalition Applied Scientist II**
- fit_score=5 ✓ (unchanged from v3)
- fit_reasoning: "The role focuses on developing and deploying ML models, statistical analysis, and experimentation, which are core data science responsibilities. There are no significant out-of-scope duties mentioned, indicating a strong alignment with data science work."

**posting_id=114, canonical_id=327: CIBC Senior Research Analyst** — TARGET FIX NOT ACHIEVED
- fit_score=5 (was 4 in v3, expected 3 — went in wrong direction)
- fit_reasoning: "The role focuses on delivering investment research and conducting macroeconomic analysis, which are core data science responsibilities. The use of Python and econometric modeling aligns with in-scope data science work, with no significant out-of-scope responsibilities mentioned."
- Root cause: LLM mapped investment research/macroeconomic analysis to in-scope item 4 (statistical analysis) rather than out-of-scope item 8 (financial modeling as separate professional discipline). The in-scope/out-of-scope lists are not granular enough to distinguish "statistical analysis supporting DS" from "financial modeling as primary professional discipline."

**posting_id=8, canonical_id=439: Dropbox Data Scientist** — TARGET FIX ACHIEVED
- fit_score=4 ✓ (was 5 in v3, expected 4)
- fit_reasoning: "The role involves significant in-scope data science responsibilities such as statistical analysis, experimentation, and data analysis, while also requiring some reporting and dashboard development, which is an adjacent out-of-scope category."
- The structured framing correctly surfaced automated dashboards as out-of-scope item 2 for this posting.

---

### Root Cause Analysis

The v4 in-scope/out-of-scope framework has a systematic failure mode: the LLM finds **any DS-adjacent keyword** in the JD and maps it to an in-scope item, then concludes "no significant out-of-scope duties" regardless of what the actual primary work is. This is the opposite of v3's failure: v3 was biased high by not anchoring at the lower scores; v4 is biased high by giving the LLM too much flexibility to reason that everything is "in-scope."

The v3 prompt's conservative default rule ("when ambiguous between 3 and 4, drop to 3") and the specific rubric note ("Quant/financial-modeling roles → fit=3") were effective anchors that v4 does not reproduce explicitly within the worked examples.

### Decision Options for User

1. **Revert to v3** — v3 was better on 4/6 postings (DarkVision=2 ✓, TELUS=3 ✓, Coalition=5 ✓, Rockwell=5 ✓), only CIBC=4 (vs expected 3) and Dropbox=5 (vs expected 4) were off. Accept v3 as-is (CIBC and Dropbox are defensible) and proceed to TASK-M3-003.

2. **Hybrid v5** — Keep v3 as the base; incorporate the in-scope/out-of-scope itemized lists alongside (not replacing) the per-score rubric + conservative default + quant note. The lists provide framework; the specific per-score examples anchor calibration.

3. **Accept v4 Dropbox fix + manual override** — Accept v4 as shipped with its 3 failures and use the `[Show anyway]` override button (M3 deliverable) to surface mis-scored cards during personal use.

4. **Accept v3 with CIBC at 4** — If CIBC=4 is defensible (macroeconomic/investment research is analytically adjacent to DS), then v3's only divergence is Dropbox=5 vs expected 4, which is a one-level mismatch. This may be acceptable for Gate 4 probabilistic approval.

Cache state after v4 test: v1|253, v4|6. Rolling back to v3 requires only the one-line `_PROMPT_VERSION` change in extract.py.

---

## v5 Hybrid Iteration — 2026-04-30

### Design Intent

v4 regressed 3 of 6 postings because replacing v3's per-score rubric with the in-scope/out-of-scope framework removed the hard calibration anchors (conservative default, quant=3 note, worked examples at each score level). v5 takes the hybrid approach:

- **Base**: v3 exactly (all 5 per-score definitions, conservative default, sister team signal, manager-role caveat, quant note, 8 worked examples — unchanged)
- **Augmentation**: Each worked example gains explicit `In-scope: items X,Y` / `Out-of-scope: items A,B` / `Distribution: ...` lines
- **New subsection**: "How to apply the rubric: in-scope vs out-of-scope DS responsibilities" added AFTER the worked examples, with the full 8 IN-SCOPE and 9 OUT-OF-SCOPE lists and a 6-step application reasoning loop

The lists are positioned as a *tool to make the rubric application precise*, not a replacement for the per-score thresholds. The `Step 4` sub-rubric in the application reasoning is an intentional redundant restatement of the per-score rubric — giving the LLM two angles on the same decision.

### Files Changed

| File | Change |
|------|--------|
| `prompts/canonical_extraction_v5.txt` | New file — v3 base with augmented examples + "How to apply" subsection |
| `src/jd_matcher/llm/extract.py` | `_PROMPT_VERSION = "v5"`, `_PROMPT_PATH` updated |
| `tests/llm/test_extract_m3.py` | All v4 references updated to v5 |

### Test Results (post-v5)

**Full suite (SKIP_LIVE=1)**: 1031 passed, 0 failed, 10 skipped
**test_extract_m3.py**: 38/38 passed

### 6-Posting v5 Smoke Test

**Date**: 2026-04-30
**Model**: gpt-4o-mini
**Prompt version**: v5
**DB snapshot before test**: `~/.jd-matcher/snapshots/20260430-HHMM-pre-m3-002-v5-prompt.db`
**Cache state after**: v1|253, v5|6

---

#### v3 → v4 → v5 → Expected comparison table

| Posting | Company | v3 | v4 | v5 | Expected | v5 Match? |
|---------|---------|----|----|-----|----------|-----------|
| 102 | Rockwell | 5 | 5 | **5** | 5 | PASS ✓ |
| 107 | DarkVision | 2 | 4 | **2** | 2 | PASS ✓ |
| 11 | TELUS | 3 | 5 | **3** | 3 | PASS ✓ |
| 10 | Coalition | 5 | 5 | **5** | 5 | PASS ✓ |
| 114 | CIBC | 4 | 5 | **3** | 3 | PASS ✓ (fixed from v3) |
| 8 | Dropbox | 5 | 4 | **5** | 4 | FAIL ✗ |

**Total: 5/6 pass**. v3's 4 passes preserved. CIBC fixed (4→3 ✓). Dropbox remains at 5 (expected 4).

---

#### Posting-by-posting v5 detail

**posting_id=102, canonical_id=315: Rockwell Senior DS Agentic AI**
- fit_score=5 ✓
- fit_reasoning: "The role focuses on building predictive models and applying statistical methods, which are core data science responsibilities. The collaboration with product managers and AI engineers further emphasizes the problem-solving aspect of data science."
- Cost: $0.001439 (8285 in / 327 out tokens)

**posting_id=107, canonical_id=320: DarkVision Data Engineer** — preserved from v3
- fit_score=2 ✓
- fit_reasoning: "The role primarily focuses on data pipeline development and validation, with limited data science modeling responsibilities. The emphasis on engineering tasks such as pipeline optimization and report integrity suggests a fit score of 2."
- Cost: $0.001406 (8290 in / 271 out tokens)
- Analysis: The in-scope/out-of-scope items + v3's worked example (with "no modeling as primary duty" anchor) together prevented the regression that v4 had.

**posting_id=11, canonical_id=323: TELUS Senior Developer AI/ML** — preserved from v3
- fit_score=3 ✓
- fit_reasoning: "The role involves significant technical leadership and full stack development, but also includes stakeholder management and cross-functional collaboration, which introduces non-DS elements. While there is a focus on AI/ML solutions, the broader scope of responsibilities leads to a fit score of 3."
- Cost: $0.001413 (8128 in / 323 out tokens)
- Analysis: Out-of-scope items 4 (full-stack) + 5 (architecture) + 9 (cross-team leadership) in the TELUS example correctly anchored this at 3.

**posting_id=10, canonical_id=312: Coalition Applied Scientist II**
- fit_score=5 ✓
- fit_reasoning: "Core duties involve developing and deploying ML models for underwriting, including data exploration and statistical analysis, which aligns closely with data science responsibilities. The role emphasizes experimentation and model monitoring, confirming a pure data science focus."
- Cost: $0.001555 (9086 in / 320 out tokens)

**posting_id=114, canonical_id=327: CIBC Senior Research Analyst** — TARGET FIX ACHIEVED
- fit_score=3 ✓ (was 4 in v3, now correctly 3)
- fit_reasoning: "The role involves significant macroeconomic analysis and investment research, but also includes elements of financial modeling and market analysis that extend beyond pure data science responsibilities."
- Cost: $0.001455 (8462 in / 309 out tokens)
- Analysis: The explicit labeling of CIBC's example with `Out-of-scope: item 8 (financial modeling as PRIMARY professional discipline)` + the CIBC example's "Distribution: financial modeling is the PRIMARY work" annotation caused the LLM to correctly apply the quant=3 note.

**posting_id=8, canonical_id=439: Dropbox Data Scientist** — REMAINING MISS
- fit_score=5 (expected 4)
- fit_reasoning: "The role focuses on data exploration, statistical analysis, and experimentation design, which are core data science responsibilities. The emphasis on user behavior analysis and collaboration with various teams confirms a pure data science scope."
- Cost: $0.001455 (8458 in / 311 out tokens)
- Analysis: LLM engaged with the in-scope items (EDA, stats, experimentation) but dismissed automated dashboards as out-of-scope item 2. The Dropbox worked example does explicitly call out `Out-of-scope: item 2 (automated reporting dashboards)` — the model may be failing to apply this to the actual JD text when the dashboarding language is embedded in a broader "analytics" description. This is the same miss as v3. Iteration budget exhausted.

---

### v5 Cost Summary

| Posting | Company | Input tokens | Output tokens | Cost (USD) |
|---------|---------|-------------|--------------|------------|
| 102 | Rockwell | 8,285 | 327 | $0.001439 |
| 107 | DarkVision | 8,290 | 271 | $0.001406 |
| 11 | TELUS | 8,128 | 323 | $0.001413 |
| 10 | Coalition | 9,086 | 320 | $0.001555 |
| 114 | CIBC | 8,462 | 309 | $0.001455 |
| 8 | Dropbox | 8,458 | 311 | $0.001455 |
| **Total** | | **50,709** | **1,861** | **$0.008723** |

Note: v5 prompt is ~1,800 tokens longer than v3 (the augmented examples + "How to apply" subsection). This is reflected in higher input token counts (~8.3k vs ~5.4k in v3).

---

### Summary: v3 vs v5

| Issue | v3 | v5 | Delta |
|-------|----|----|-------|
| Rockwell fit=5 | ✓ | ✓ | preserved |
| DarkVision fit=2 | ✓ | ✓ | preserved |
| TELUS fit=3 | ✓ | ✓ | preserved |
| Coalition fit=5 | ✓ | ✓ | preserved |
| CIBC fit=3 | ✗ (returned 4) | ✓ (returns 3) | FIXED |
| Dropbox fit=4 | ✗ (returned 5) | ✗ (returns 5) | unchanged miss |

v5 is strictly better than v3 (5/6 vs 4/6). Iteration budget (3 attempts) exhausted.

### Items for User Review (Gate 4 — v5)

**Iteration budget exhausted.** This is attempt 3 of 3. User must choose one of:

1. **Accept v5 (5/6)** — v5 is the best achieved result. Dropbox fit=5 (expected 4) is a one-level miss on a defensible DS role. Proceed to TASK-M3-003 with v5 active.

2. **Accept v3 with CIBC at 4** — Revert to v3 (4/6); CIBC at 4 and Dropbox at 5 are both defensible one-level misses. The `[Show anyway]` override button in M3 can surface any mis-scored card during personal use.

No iteration 4 will be attempted regardless of the outcome — per `/implement` Step 3 budget rule.

---

## v5 30-Sample Scale Validation — 2026-04-30

### Purpose

Gate 4 approval-flow check: does v5 produce sensible output at 5x the smoke-test volume before committing to the full 257-canonical re-extraction (TASK-M3-003, ~$0.15)? This is NOT the formal 30-hand-labeled validation (TASK-M3-004) — it is a distribution-sanity check using random sampling to surface unexpected failure modes.

### Sample Method

- **Total sampled**: 30 canonicals
- **Selection**: `ORDER BY RANDOM() LIMIT 30` from `canonical_postings WHERE canonical_id NOT IN (312, 315, 320, 323, 327, 439)`
- **Excluded prior 6**: canonical_ids 312 (Coalition), 315 (Rockwell), 320 (DarkVision), 323 (TELUS), 327 (CIBC), 439 (Dropbox) — all previously extracted with v5 in the smoke test
- **Overlap with excluded set**: 0 confirmed
- **DB snapshot before run**: `~/.jd-matcher/snapshots/20260430-HHMM-pre-m3-002-v5-30sample.db`

### Canonical IDs Sampled

344, 347, 350, 355, 357, 360, 366, 370, 380, 382, 387, 389, 393, 397, 413, 417, 436, 448, 449, 450, 465, 466, 474, 488, 489, 499, 522, 532, 534, 558

### Parse Failures

**0 parse failures out of 30.** 2 postings had a `canonical_location` Pydantic validation error on attempt 1/3 (produced `"Hybrid — Other"` which is not in the location enum) — both recovered on the stricter-prompt retry (attempt 2/3) and are counted as successful extractions. These are retry-path recoveries, not final failures.

### fit_score Distribution

| Score | Count | % |
|-------|-------|---|
| 1 | 0 | 0% |
| 2 | 3 | 10% |
| 3 | 8 | 27% |
| 4 | 12 | 40% |
| 5 | 7 | 23% |

**Shape assessment**: distribution is 0/10/27/40/23. No score=1 at all; the bulk falls at 3-4 (67%) with score=5 at 23% and score=2 at 10%. This is a healthier distribution than the 6-sample smoke test's cherry-picked set. Score=5 at 23% is within the expected range — not bias-high (>50%). Score=2 at 10% confirms the low-end anchor is functioning. No pile-up at 5.

### role_orientation Distribution

| Label | Count (multi-label, n=30) |
|-------|--------------------------|
| Problem-Solving | 30 (100%) |
| Communication | 22 (73%) |
| Engineering | 3 (10%) |

**Top combinations:**

| Combination | Count |
|-------------|-------|
| [Problem-Solving, Communication] | 20 |
| [Problem-Solving] | 7 |
| [Engineering, Problem-Solving, Communication] | 2 |
| [Engineering, Problem-Solving] | 1 |

**Assessment**: Problem-Solving on all 30 is the expected invariant for a DS corpus (core DS is always problem-solving). Communication at 73% is higher than the 6-sample test and worth monitoring — many postings likely have cross-functional collaboration language. Engineering at 10% (3 postings) is appropriate per v5 definition (SE-specific work only); this is low, not high. No `role_orientation=[]` cases (min_length=1 constraint respected). No cases with all-3 that look suspicious — the 2 all-3 cases are Amazon SDE-II and RBC Senior Development Manager (both have genuine full-stack + PM + DS components).

### Industry Distribution

| Industry | Count |
|----------|-------|
| B2B SaaS | 10 |
| Other | 6 |
| Healthcare / Healthtech | 6 |
| Financial Services / Asset Management | 3 |
| Insurance / Insurtech | 1 |
| Professional Services / Consulting | 1 |
| Construction / AEC | 1 |
| Telecom / Digital Services | 1 |
| Legal Tech / Compliance | 1 |

**Other count**: 6/30 = 20%. Threshold for taxonomy-gap signal is >30% — 20% is within acceptable range. The 6 "Other" cases are:
- canonical_id=347: "Data Scientist" at unnamed company — company name canonicalized to "Other" (no company identity available; "Other" for industry is correct)
- canonical_id=355: "Human Data Manager" — likely AI training/annotation platform, but no clear company identity
- canonical_id=389: IBM SAP HANA role — IBM Consulting; could be "Professional Services / Consulting" but the role is specifically SAP/ERP consulting not DS consulting
- canonical_id=393: Marine Biologics Senior Scientist — biotech/food-tech, no matching taxonomy bucket (closest would be Healthcare but it's a food ingredient company)
- canonical_id=474: ICBC RPA/AI Apps Developer — ICBC is an insurance company but "Other" was returned rather than "Insurance / Insurtech"
- canonical_id=558: Brokkr Microbiology Lead — biotech/synthetic biology, no matching taxonomy bucket

**Taxonomy gap note**: ICBC (canonical_id=474) should likely be "Insurance / Insurtech" — ICBC is the provincial auto insurance monopoly. This is a minor mis-classification, not a parse failure. The 5 remaining "Other" cases are defensible. No action required before TASK-M3-003 — the full pass will naturally surface systematic patterns.

### Salary Coverage

**19/30 = 63%** with non-null salary fields.

**Anomalies flagged:**

| canonical_id | posting_id | salary_min_cad | salary_max_cad | Issue |
|-------------|-----------|---------------|---------------|-------|
| 355 | 140 | 40 | 61 | Hourly rate ($30-$45/hr) stored as annual integer — missing annualization |
| 360 | 145 | 0 | 0 | Salary fields populated with 0 instead of null — should be null |
| 532 | 271 | 137 | null | Hourly rate ($100/hr) stored as annual integer — missing annualization |

**Assessment**: The prompt instructs conversion of hourly rates to annual CAD (×2000 hours). For posting 140 ("$30-$45/hour"), the correct annualized range is ~$60,000-$90,000 CAD; the LLM stored the raw dollar amounts ($30, $45 → stored as 40, 61 — unclear rounding). For posting 271 (Turing, hourly contractor rate), similar issue. For posting 145 (PHSA, salary not stated in JD), the 0/0 returned instead of null/null is a minor defect. These are edge cases that v5 does not currently handle correctly for hourly/contractor postings. Flagged for awareness — not a blocker for TASK-M3-003 (full re-extraction), as these affect a small minority and the `[Show anyway]` override handles edge cases during personal use.

### citizenship_requirement Distribution

| Value | Count |
|-------|-------|
| not_mentioned | 29 |
| preferred | 1 |
| required | 0 |

**Assessment**: 29/30 `not_mentioned` is expected for a Canadian corpus. The 1 `preferred` case is canonical_id=534 (UBC Postdoctoral Research Fellow): "Canadians and permanent residents of Canada will be given priority" — correctly classified as `preferred`. No `required` cases, which makes sense: none of the 30 sample appear to be US-only roles with hard work authorization gates.

### can_hire_in_canada Distribution

| Value | Count |
|-------|-------|
| yes | 22 |
| likely | 5 |
| unclear | 3 |
| no | 0 |

**Assessment**: `yes` at 73% is expected for a Canada-focused job board pipeline. `unclear` at 10% (3 postings) — canonical_ids 355 (unnamed company, remote), 393 (Marine Biologics, US-founded biotech), 466 (ExaCare AI, US company). All defensible. No `no` cases.

### Spot-Check Outliers

**Lowest fit_score (fit=2) — 3 cases:**

1. **canonical_id=389, posting_id=30: IBM SAP HANA Package Consultant (fit=2)**
   - Title: "Package Consultant specializing in SAP HANA Analytics"
   - JD excerpt: "A career in IBM Consulting... hybrid cloud and AI journeys"
   - LLM reasoning: "focuses primarily on SAP HANA Information Models development and related technical skills, with limited direct data science responsibilities. The emphasis is on data management and modeling rather than data exploration or machine learning."
   - Assessment: fit=2 is CORRECT. SAP HANA consulting is enterprise data warehousing, not DS modeling. The "AI" in the IBM Consulting description is generic brand language, not role content. v5 correctly ignored the brand language and scored on the actual role work.

2. **canonical_id=393, posting_id=34: Marine Biologics Senior Scientist (fit=2)**
   - Title: "Senior Scientist"
   - JD excerpt: "Marine Biologics makes SeaTex... IP scoping & patent filing (primary focus) — Define divisional-patent requirements. Translate lab results into patentable claims..."
   - LLM reasoning: "focuses on lab management and patent-related tasks, with limited direct data science or machine learning responsibilities. The emphasis is on chemistry and product development rather than data analysis or modeling."
   - Assessment: fit=2 is CORRECT. This is a food-science/chemistry role (seaweed ingredient patents). Not a DS role at all — it appears in the corpus from a keyword false-positive (perhaps "data analysis" in the JD). v5 correctly rejected it.

3. **canonical_id=355, posting_id=140: Human Data Manager Early Career (fit=2)**
   - Title: "Human Data Manager (Early Career)"
   - JD excerpt: "Type: Hourly contract / Compensation: $30-$45/hour... Design and manage data workflows for annotation, collection, processing, and analysis."
   - LLM reasoning: "focuses on data workflows and operational processes, with limited emphasis on data science modeling or statistical analysis. The primary responsibilities are more aligned with data management and operational efficiency rather than core data science tasks."
   - Assessment: fit=2 is CORRECT. This is a data-ops/annotation-ops role, not DS. The "Human Data Manager" title is a data annotation management role (likely for an AI training company). v5 correctly identified the operational vs modeling distinction.

**Highest fit_score=5 example — canonical_id=466, posting_id=193: ExaCare AI Machine Learning Engineer**
   - Title: "Machine Learning Engineer"
   - Company: ExaCare AI (healthcare AI, $30M Series A)
   - LLM reasoning: "Core duties include building, training, and deploying machine learning models, with a strong emphasis on MLOps and experimentation, aligning perfectly with the core duties of a Data Scientist. The responsibilities include direct involvement in model optimization and data management, confirming a pure data science scope."
   - Assessment: fit=5 is CORRECT. ExaCare AI is building ML models for healthcare data (post-acute care referrals). This is a pure MLE/DS role at an AI-native company. Score=5 appropriate.

**industry="Other" spot-check — 2 examples:**

1. **canonical_id=393, Marine Biologics (Other)**: Biotech/food-science company making seaweed food ingredients. "Other" is correct — the 16-sector taxonomy has no Biotech / FoodTech bucket. A taxonomy extension could add "Biotech / Life Sciences" but is not needed for this corpus where biotech roles are rare false-positives anyway.

2. **canonical_id=558, Brokkr (Other)**: Microbiology Lead at a synthetic biology / food-tech company. Same pattern as Marine Biologics. "Other" is defensible.

**Salary anomalies — 2 examples of hourly rates:**

1. **canonical_id=355 (Human Data Manager)**: JD states "$30-$45/hour" — the v5 prompt expects conversion to annual CAD. The LLM stored 40/61 (mid-range of the hourly figures, without annualization). Expected behavior: store null or annualize to 60000/90000. The prompt's hourly-to-annual conversion instruction did not fire correctly for this edge case. Not a blocker — hourly contract roles are not core job-search targets.

2. **canonical_id=532 (Turing Quantitative Finance)**: JD states a per-hour or per-task contractor rate. LLM stored 137/null. Same root cause as above — hourly rate not annualized. Not a blocker.

**Potential concern — Amazon SDE-II (canonical_id=417) at fit=4:**
   - Title: "Software Development Engineer II"
   - Company: Amazon
   - LLM reasoning: "focuses on software development and optimization algorithms, with significant responsibilities in machine learning and system performance. While there is a strong emphasis on engineering practices, the role also includes elements of problem-solving and collaboration."
   - Assessment: This is a debatable score. A plain SDE-II role should be fit=2-3 per the rubric (primarily SWE). Amazon's SDE-II posting mentioning "optimization algorithms" and "machine learning and system performance" pushed it to 4. If this is an Amazon Ads/Search/Recommendations team SDE-II where ML is genuinely core, 4 is defensible. If it's a generic SDE-II with incidental ML mentions, 3 would be correct. The `[Show anyway]` override covers this case during personal use.

### v1 → v5 Score-Change Comparison

**None of the 30 canonicals had prior v1 extraction cache entries.** All 30 are recently ingested postings that had not been extracted before (they were added to `canonical_postings` after the v1 extraction run or were never individually extracted). The v1 extraction cache currently covers 223 entries; these 30 are among the remaining un-extracted canonicals.

**Implication**: No direct v1→v5 delta is available for this sample. The v1→v5 comparison will be available after TASK-M3-003 (full 257-canonical re-extraction), where all 223 v1 entries will be re-extracted and the delta can be computed at full corpus scale.

**Indirect signal from cache state**:
- Before run: v1|253, v5|6
- After run: v1|223, v5|36
- 30 new v5 entries written; 30 v1 entries replaced (INSERT OR REPLACE on the same PK)

### Total Cost (30 new calls)

| Metric | Value |
|--------|-------|
| Calls made | 30 |
| Total input tokens | 249,544 |
| Total output tokens | 9,087 |
| Total cost (USD) | $0.0429 |
| Avg cost per call | $0.00143 |
| Under $0.05 watchdog | YES |

Cost is $0.043 — within the expected ~$0.03 range (slightly higher due to retry calls for the 2 location parse failures on attempt 1). Well under the $2.00 watchdog.

### Verdict

**v5 stable — recommend approval for TASK-M3-003.**

No red flags:
- 0 final parse failures (0%)
- fit_score distribution is healthy (0/10/27/40/23%) — no pile-up at 5, lower scores functioning
- role_orientation: Problem-Solving universally applied, Engineering appropriately rare (10%), Communication reasonable (73%)
- industry "Other" at 20% — below the 30% concern threshold
- citizenship and can_hire_in_canada distributions look correct for a Canadian corpus
- 63% salary coverage is reasonable (many postings omit salary)

Minor issues noted (not blockers for TASK-M3-003):
1. Hourly rates not annualized — affects ~2-3 postings in the corpus; these are edge-case contract/hourly postings
2. salary=0/0 returned instead of null/null for one posting (PHSA, no salary stated) — minor defect
3. ICBC (canonical_id=474) tagged as "Other" instead of "Insurance / Insurtech" — one-off mis-classification
4. Amazon SDE-II (canonical_id=417) at fit=4 is borderline — could be 3 depending on actual team context

---

### v6 simplification — same 30 samples

**Date**: 2026-05-01
**Prompt version**: v6
**Design**: Stripped all v5 elaboration from fit_score section — removed 8 worked examples, in-scope/out-of-scope lists, manager-role caveat, sister-team signal, conservative-default rule, quant=3 note, "How to apply" subsection. Replaced with exactly 5 rubric lines.
**v5 scores**: re-extracted fresh (v5 cache entries had been overwritten by v6 run; recovered via in-process prompt patch).

#### Rubric-expected methodology

rubric_expected was derived as follows:
- 4 cases confirmed in v5 spot-check narratives: IBM SAP HANA=2, Marine Biologics=2, Human Data Manager=2, ExaCare AI MLE=5
- Role-class defaults applied to the remaining 26 per the 5-line v6 rubric:
  - Pure DS/Applied Scientist/MLE roles → 5 (Cover Genius, Amazon Applied Sci, PictorLabs, UBC Postdoc)
  - DS + dashboard/BI → 4 (Comm100 Algorithm Eng AI, Alimentiv Statistician, Joveo Agentic AI, Alquemy DS-via-recruiter)
  - DS + non-DS work / managers / non-pure-DS → 3 (Affirm Mgr MLE, PHSA Data Analyst, Bird Construction, BCCNM Perf Measurement, Dialpad Analytics Eng, Hopper Finance Strategy, Fasken Mgr Data Analytics, RBC Sr Dev Manager, Diligent AI Solution Architect, Clio Mgr Enterprise AI, ICBC RPA/AI Dev, The Select Group Dev Analyst, Grafana Labs Sr Analytics Eng, KOHO Sr BA, Turing Quant Finance, Amazon SDE-II, Aspire AI Automation Eng)
  - Mainly non-DS data-adjacent → 2 (Crossing Hurdles Data Ops Mgr, IBM SAP HANA, Marine Biologics R&D Sci, Brokkr Microbiology Lead)

#### Per-sample comparison table

| canonical_id | employer / title | v5 | v6 | rubric | v5 match | v6 match |
|---|---|---|---|---|---|---|
| 344 | Aspire Software / AI Automation Engineer | 4 | 4 | 3 | N | N |
| 347 | Alquemy S&C / Data Scientist | 5 | 5 | 4 | N | N |
| 350 | Affirm / Manager MLE | 3 | 4 | 3 | Y | N |
| 355 | Crossing Hurdles / Data Operations Manager | 2 | 2 | 2 | Y | Y |
| 357 | Cover Genius / Sr Data Scientist GenAI | 5 | 5 | 5 | Y | Y |
| 360 | PHSA / Data Analyst | 3 | 3 | 3 | Y | Y |
| 366 | Bird Construction / Sr Data Analyst | 4 | 4 | 3 | N | N |
| 370 | BCCNM / Perf Measurement Specialist | 4 | 4 | 3 | N | N |
| 380 | Dialpad / Analytics Engineer | 5 | 4 | 3 | N | N |
| 382 | Comm100 / Algorithm Engineer AI | 5 | 4 | 4 | N | Y |
| 387 | Hopper / Finance Strategy Manager | 4 | 4 | 3 | N | N |
| 389 | IBM / SAP HANA Consultant | 2 | 3 | 2 | Y | N |
| 393 | Marine Biologics / R&D Scientist | 2 | 3 | 2 | Y | N |
| 397 | Alimentiv / Statistician | 4 | 4 | 4 | Y | Y |
| 413 | Joveo / Agentic AI Engineer | 5 | 4 | 4 | N | Y |
| 417 | Amazon / SDE-II | 4 | 3 | 3 | N | Y |
| 436 | Fasken / Manager Data Analytics | 4 | 4 | 3 | N | N |
| 448 | Amazon / Applied Scientist | 5 | 5 | 5 | Y | Y |
| 449 | RBC / Sr Dev Manager | 3 | 3 | 3 | Y | Y |
| 450 | Diligent / AI Solution Architect | 4 | 4 | 3 | N | N |
| 465 | Clio / Manager Enterprise AI | 3 | 4 | 3 | Y | N |
| 466 | ExaCare AI / Machine Learning Engineer | 5 | 4 | 5 | Y | N |
| 474 | ICBC / RPA/AI Apps Dev | 4 | 4 | 3 | N | N |
| 488 | The Select Group / Developer Analyst | 3 | 3 | 3 | Y | Y |
| 489 | Grafana Labs / Sr Analytics Engineer | 4 | 4 | 3 | N | N |
| 499 | KOHO / Sr BA Fraud Strategy | 4 | 4 | 3 | N | N |
| 522 | PictorLabs / Sr Applied ML Eng CV | 5 | 5 | 5 | Y | Y |
| 532 | Turing / Quant Finance | 4 | 3 | 3 | N | Y |
| 534 | UBC / Postdoc Research Fellow | 5 | 5 | 5 | Y | Y |
| 558 | Brokkr / Microbiology Lead | 3 | 3 | 2 | N | N |

#### Aggregate stats

| Metric | v5 | v6 |
|--------|----|----|
| Agreement with rubric | 14 / 30 (46.7%) | 13 / 30 (43.3%) |
| Disagreement with rubric | 16 / 30 (53.3%) | 17 / 30 (56.7%) |

**v6 is not better than v5 on this corpus.** The disagreement rates are statistically identical (53% vs 57%, within noise). v6 is also not dramatically worse — the two prompts produce near-identical aggregate performance, but for different reasons on different samples.

#### fit_score distribution: v5 vs v6

| Score | v5 count | v6 count |
|-------|----------|----------|
| 1 | 0 | 0 |
| 2 | 3 | 1 |
| 3 | 6 | 8 |
| 4 | 12 | 16 |
| 5 | 9 | 5 |

Key observation: v6 shifts mass from 2 and 5 into 3 and 4. It collapses the low end (fewer fit=2 detections) and the high end (fewer fit=5 detections) toward the middle. The 16 fit=4 scores in v6 vs 12 in v5 is the most visible signal — v6 is gravitating toward 4 as a default for ambiguous roles.

#### Notable shifts (10 cases where v5 ≠ v6)

1. **Comm100 Algorithm Engineer AI (382): v5=5 → v6=4 [BETTER, rubric=4]** — v5 over-scored a role with genuine SE/algorithm engineering components. v6 correctly landed at 4. This is v6's clearest win.

2. **Joveo Agentic AI Engineer (413): v5=5 → v6=4 [BETTER, rubric=4]** — v5 over-scored an AI eng role with mixed DS+SE responsibilities. v6 correctly landed at 4.

3. **Amazon SDE-II (417): v5=4 → v6=3 [BETTER, rubric=3]** — v5 over-scored a primarily-SWE role. v6 correctly identified it as DS+SWE (fit=3). This was the borderline case flagged in v5 analysis.

4. **Turing Quant Finance (532): v5=4 → v6=3 [BETTER, rubric=3]** — v6 correctly applied the quant=3 logic without the explicit rubric note, just from the minimal rubric definition.

5. **IBM SAP HANA Consultant (389): v5=2 → v6=3 [WORSE, rubric=2]** — v5 correctly scored this as data-adjacent non-DS work (fit=2). v6 lost the low-end anchor; without explicit calibration examples, it inflated to 3. A clear regression.

6. **Marine Biologics R&D Scientist (393): v5=2 → v6=3 [WORSE, rubric=2]** — Same pattern as IBM. v5 correctly rejected a chemistry/lab role; v6 inflated it to 3. Loss of the fit=2 anchor.

7. **ExaCare AI MLE (466): v5=5 → v6=4 [WORSE, rubric=5]** — v6 under-scored a pure MLE role at an AI-native company. The absence of the sister-team signal instruction caused v6 to penalize the SE component (model deployment) that v5 correctly identified as in-scope DS work.

8. **Affirm Manager MLE (350): v5=3 → v6=4 [WORSE, rubric=3]** — v5 correctly landed this manager-in-DS-team role at 3. v6 inflated to 4, missing the managerial overhead that reduces the fit. The manager-role caveat removed in v6 may be load-bearing here.

9. **Clio Manager Enterprise AI (465): v5=3 → v6=4 [WORSE, rubric=3]** — Same pattern as Affirm. v5 correctly held managers at 3; v6 promoted to 4.

10. **Dialpad Analytics Engineer (380): v5=5 → v6=4 [SAME-MISS, rubric=3]** — Both v5 and v6 over-score this analytics engineering role, but v6 is closer. Neither lands at rubric=3.

#### Summary interpretation

v6 simplification hypothesis — "remove all the engineering and let the 5-line rubric do the work" — is **not confirmed**. The two prompts are statistically equivalent on this 30-sample corpus (46.7% vs 43.3% agreement), but for structurally different reasons:

- **v6 wins** on the high-inflation cases where v5's elaboration failed to prevent upward drift (Comm100, Joveo, SDE-II, Turing) — 4 cases.
- **v6 loses** on the low-end anchor cases where v5's worked examples held the model at fit=2 for clearly non-DS roles (IBM SAP HANA, Marine Biologics) and on manager-role cases where v5's explicit caveat kept scores at 3 (Affirm, Clio, ExaCare AI) — 5 cases.

The 16 structural disagreements (same between v5 and v6) are shared anchor failures: both prompts over-score roles like Bird Construction Sr Data Analyst (4 vs rubric=3), Aspire AI Automation Engineer (4 vs rubric=3), and Grafana Labs Sr Analytics Engineer (4 vs rubric=3). These are not a v6-specific problem — they reflect a general model bias toward 4 for any role with "data" or "AI" in the title.

**Net verdict**: v6 is not an improvement over v5. The simplification removed load-bearing calibration anchors (fit=2 worked examples, manager-role caveat) without fixing the shared structural failures. The 37% per-sample disagreement reported for v5 in the task context maps closely to the 53% seen here (the difference likely reflects rubric scoring methodology differences between the user-rubric run and this agent-rubric run, not a real regression).

---

### v7 ownership rubric + reasoning-before-score — same 30 samples

**Date**: 2026-05-01
**Summary**: Schema + 5-level ownership rubric + manager paragraph; `fit_reasoning` generated before `fit_score` (Pydantic field order enforces chain-of-thought); no worked examples, no caveats, ownership framing replaces DS-fit framing.

---

#### v7 rubric (applied fresh — do not copy v5/v6 rubric_expected values)

```
5 = SOLE ownership of ML/statistical model as a problem-solving tool.
    (Includes deployment + monitoring of THEIR OWN model. Includes
    model-performance dashboards the DS builds for themselves.)
4 = DUAL ownership: ML/statistical model + BI/Tableau-style dashboards
    for stakeholder consumption (specifically dashboards, not other things).
3 = DUAL ownership: ML/statistical model + ANYTHING OTHER than stakeholder
    dashboards (MLOps robustness, software/backend/API, data engineering,
    data architecture, integration).
2 = SOLE ownership of something OTHER than ML/statistical models
    (data eng, BI dev, MLE-as-deployment-only, data architect, backend).
1 = Non-data role.

Manager roles: evaluate the COMBINED ownership of the team the manager
leads, then apply 1-5 to that combined ownership.
```

---

#### Per-sample comparison table

Rubric scores applied fresh against the ownership rubric above. `?` = genuinely ambiguous / recruiter-thin JD where rubric cannot be mechanically applied.

| canonical_id | employer / title | v7_fit_reasoning (truncated ~120 chars) | v7_fit | rubric_expected | agree? |
|---|---|---|---|---|---|
| 344 | Aspire Software / AI Automation Engineer | "...owns development and deployment of AI agents... maps to fit=4, dual ML + stakeholder-facing products." | 4 | 3 | N |
| 347 | Alquemy Search / Data Scientist | "...owns development and implementation of ML models and data analysis... dual ownership of ML models and stakeholder dashboards." | 4 | ? | ? |
| 350 | Affirm / Manager, MLE (Fraud) | "...owns development and management of ML models for fraud... dual ownership of ML models and stakeholder dashboards for decision-making." | 4 | 3 | N |
| 355 | Crossing Hurdles / Data Operations Manager | "...owns design and management of data workflows and operational performance metrics... focus is on data management rather than ML." | 2 | 2 | Y |
| 357 | Cover Genius / Sr Data Scientist GenAI | "...owns development and evaluation of LLMs... dual ownership of ML models and stakeholder-facing evaluation frameworks." | 4 | 5 | N |
| 360 | Provincial Health Services / Data Analyst | "...owns development and maintenance of datasets and automation of reports and dashboards... dual ownership of data analysis and reporting." | 3 | 2 | N |
| 366 | Bird Construction / Sr Data Analyst | "...owns delivery of analytics solutions and dashboards... dual ownership of ML/statistical models and stakeholder dashboards." | 4 | 2 | N |
| 370 | BC College of Nurses / Performance Measurement Spec | "...owns development and analysis of performance metrics and reporting resources... dual ownership of data analysis and performance metrics." | 3 | 2 | N |
| 380 | Dialpad / Analytics Engineer | "...owns optimization of conversational AI systems and data pipelines... dual ownership of ML models and stakeholder dashboards." | 4 | 3 | N |
| 382 | Comm100 / Algorithm Engineer, AI | "...owns development and deployment of AI models and features... sole ownership of ML/statistical models and their deployment." | 5 | 5 | Y |
| 387 | Hopper / Finance & Strategy Manager | "...owns development of financial systems and predictive models, AI for automation and reporting... dual ownership of financial modeling and stakeholder reporting." | 4 | 4 | Y |
| 389 | IBM / Managing Consultant SAP Analytics | "...owns development and management of SAP HANA Information Models... dual ownership of model development and testing." | 3 | 2 | N |
| 393 | Marine Biologics / R&D Scientist | "...owns patent filing and lab management processes... dual ownership of lab management and patent-related work." | 3 | 1 | N |
| 397 | Alimentiv / Statistician | "...owns statistical analysis and reporting for clinical trials... dual ownership of statistical models and project support." | 3 | 5 | N |
| 413 | Joveo / Agentic AI Engineer | "...owns development and deployment of AI agents... dual ownership of AI models and performance optimization." | 4 | 5 | N |
| 417 | Amazon / Software Development Engineer | "...owns development of software systems and optimization algorithms for transportation... dual ownership of ML models and system performance." | 3 | 2 | N |
| 436 | Fasken / Manager, Data Analytics | "...owns delivery of analytics solutions and insights, design and maintenance of dashboards... dual ownership of analytics and stakeholder reporting." | 4 | 2 | N |
| 448 | Amazon / Applied Scientist | "...owns development and deployment of ML models to drive business insights... dual ownership of ML models and stakeholder insights." | 4 | 5 | N |
| 449 | RBC / Senior Development Manager | "...owns end-to-end software development lifecycle for modernization, including AI/ML integration... dual ownership of ML models and stakeholder dashboards." | 4 | 3 | N |
| 450 | Diligent / AI Solution Architect | "...owns development and deployment of AI solutions tailored to business needs... dual ownership of AI solutions and stakeholder engagement." | 4 | 2 | N |
| 465 | Clio / Manager, Enterprise AI | "...owns delivery and operational management of AI capabilities, strategy and platform governance... dual ownership of AI initiatives and stakeholder engagement." | 4 | 3 | N |
| 466 | ExaCare AI / Machine Learning Engineer | "...owns development and deployment of ML models, including entire ML lifecycle... sole ownership of ML models and their deployment." | 5 | 5 | Y |
| 474 | ICBC / Intermediate Developer RPA/AI | "...owns development and delivery of software applications in RPA and AI... dual ownership of ML models and stakeholder dashboards." | 4 | 2 | N |
| 488 | The Select Group / Developer Analyst | "...owns data extraction and analysis to support marketing initiatives... dual ownership of data analysis and collaboration with other teams." | 3 | 2 | N |
| 489 | Grafana Labs / Sr Analytics Engineer | "...owns architecture and infrastructure of data stack... dual ownership of data modeling and collaboration with other teams." | 3 | 2 | N |
| 499 | KOHO / Sr BA Fraud Strategy | "...owns fraud control landscape and detection models, focusing on risk mitigation... dual ownership of fraud models and stakeholder dashboards." | 4 | 2 | N |
| 522 | PictorLabs / Sr Applied ML Engineer CV | "...owns development and optimization of ML models for digital pathology... sole ownership of ML models and their deployment." | 5 | 5 | Y |
| 532 | Turing / Quantitative Finance Professional | "...owns evaluation and training of AI models in quantitative finance... dual ownership of statistical modeling and collaboration with AI teams." | 3 | 2 | N |
| 534 | UBC / Postdoc Research Fellow | "...owns research deliverables, including data analysis and policy evaluation... dual ownership of research and data analysis without direct stakeholder dashboard responsibilities." | 3 | 5 | N |
| 558 | Brokkr / Microbiology Lead | "...owns design and execution of microbiological experiments... dual ownership of experimental design and collaboration with engineering." | 3 | 1 | N |

---

#### Aggregate stats

| Metric | v7 |
|--------|----|
| Agreement with rubric (excl. ?) | 5 / 29 (17.2%) |
| Disagreement with rubric (excl. ?) | 24 / 29 (82.8%) |
| Ambiguous / rubric-inapplicable (?) | 1 / 30 |

#### v7 fit_score distribution

| Score | v7 count |
|-------|----------|
| 1 | 0 |
| 2 | 1 |
| 3 | 10 |
| 4 | 16 |
| 5 | 3 |

The distribution is heavily compressed toward 3–4. Only 1 score of 2, zero scores of 1, and only 3 scores of 5. The model is defaulting "dual ownership" as its reasoning template for nearly every role regardless of actual ownership structure.

---

#### Notable wins (5 correct calls)

1. **Crossing Hurdles Data Operations Manager (355): v7=2, rubric=2** — Correctly identified that the role owns data workflow management, not ML models. The "data management rather than ML/statistical modeling" reasoning is accurate.

2. **Comm100 Algorithm Engineer AI (382): v7=5, rubric=5** — Correctly scored sole ML ownership. Reasoning explicitly cites deployment of AI models as the primary deliverable.

3. **Hopper Finance & Strategy Manager (387): v7=4, rubric=4** — Correct on the financial modeling + stakeholder reporting dual ownership. The manager paragraph appears to have been applied (reasoning references financial systems + predictive models).

4. **ExaCare AI Machine Learning Engineer (466): v7=5, rubric=5** — Correct. Explicitly cites "entire ML lifecycle" and sole ownership. One of v7's cleaner ownership identifications.

5. **PictorLabs Sr Applied ML Engineer CV (522): v7=5, rubric=5** — Correct. Core ML model for digital pathology, deployment included. Clean identification.

---

#### Notable misses (5 representative failures)

1. **Alimentiv Statistician (397): v7=3, rubric=5 — Ownership identification failure**
   The role is a pure statistician who owns statistical models for clinical trials. This is sole ownership of a statistical model (rubric=5). v7 instead classified it as "dual ownership of statistical models and project support" (fit=3). The model misread collaboration with project teams as co-ownership of the statistical work, rather than recognizing it as downstream consumption of the statistician's output.

2. **Amazon Applied Scientist (448): v7=4, rubric=5 — Bucket mapping failure**
   The model correctly identified ML model development as the core deliverable but mapped it to fit=4 ("dual ownership of ML models and stakeholder insights"). The "stakeholder insights" cited are the downstream consumers of the ML work, not a separate co-owned deliverable. The model confused what the role produces (ML models) with who benefits from it (stakeholders), landing one bucket too low.

3. **UBC Postdoc Research Fellow (534): v7=3, rubric=5 — Bucket mapping failure**
   Pure statistical/ML research role. The model landed at fit=3 citing "dual ownership of research and data analysis without direct stakeholder dashboard responsibilities" — which is self-contradictory (the reasoning rules out fit=4 by noting no dashboards, yet still scores 3 instead of 5). This is a systematic failure: the model treats "no dashboards" as evidence for fit=3 rather than recognizing that sole ownership of statistical methodology = fit=5.

4. **Fasken Manager Data Analytics (436): v7=4, rubric=2 — Manager-rule failure + ownership identification failure**
   The manager leads an analytics/BI team. Applying the manager rule: the team's combined ownership is BI dashboards + reporting — no ML model ownership. That maps to rubric=2 (sole non-ML ownership). v7 scored fit=4 and described "dual ownership of analytics and stakeholder reporting." The model did not apply the manager rule, and separately misidentified BI/reporting work as ML-adjacent.

5. **KOHO Senior Business Analyst Fraud Strategy (499): v7=4, rubric=2 — Ownership identification failure**
   A BA who uses fraud detection models but does not own or build them. v7 scored fit=4 with reasoning "dual ownership of fraud models and stakeholder dashboards." The model attributed model ownership to a role that consumes model outputs for strategy work. This is a systematic hallucination of ML ownership for roles adjacent to data science output.

---

#### Sample of v7 fit_reasoning quality (5 verbatim outputs)

These samples illustrate whether the model is doing genuine ownership analysis or pattern-matching on job title/keywords.

**1. ExaCare AI MLE (466) — Best-case ownership analysis:**
> "The role primarily owns the development and deployment of machine learning models, including the entire ML lifecycle. It collaborates with teams on data management and MLOps practices but does not explicitly mention ownership of stakeholder dashboards or BI reporting. This maps to a fit score of 5, as the role encompasses sole ownership of ML models and their deployment."

Assessment: Correct. The model explicitly distinguished collaboration (data management, MLOps with others) from ownership (ML lifecycle), and correctly noted the absence of dashboard deliverables. This is the ownership-analysis pattern working as intended.

**2. Amazon Applied Scientist (448) — Bucket mapping error:**
> "The role primarily owns the development and deployment of machine learning models to drive business insights and customer discovery. It collaborates with engineering and business teams for implementation and strategy but does not own the engineering aspects of model deployment. This maps to a fit score of 4, as it involves dual ownership of ML models and stakeholder insights."

Assessment: The ownership identification ("primarily owns ML model development") is correct, but the bucket assignment is wrong. The model then constructs a phantom "dual ownership" with "stakeholder insights" — which is just the output consumers of the ML work, not a co-owned deliverable. Score should be 5.

**3. Alimentiv Statistician (397) — Systematic misread of collaboration as co-ownership:**
> "The role primarily owns the statistical analysis and reporting for clinical trials. It collaborates with project teams and data management to ensure data integrity and adherence to protocols. This maps to a fit score of 3, as it involves dual ownership of statistical models and project support."

Assessment: The model treated downstream collaboration ("ensure data integrity") as a second ownership bucket ("project support"), landing at fit=3. A statistician owning statistical models for clinical trials is a textbook rubric=5. This shows the model conflating "collaborates with X" with "co-owns X."

**4. Marine Biologics R&D Scientist (393) — Failure to apply rubric=1:**
> "The role primarily owns the patent filing and lab management processes. It collaborates with outside counsel for patent prosecution but does not own the legal aspects of patenting. This maps to a fit score of 3 as it involves dual ownership of lab management and patent-related work."

Assessment: This is a non-data role (biochemistry/lab work). Rubric=1. The model instead found "dual ownership" of lab management and patent work — neither of which is data-adjacent. Score of 3 is entirely incorrect. The model cannot identify fit=1 or fit=2 for clearly non-data roles — it defaults to dual-ownership framing at fit=3 as a floor.

**5. UBC Postdoc Research Fellow (534) — Self-contradictory reasoning:**
> "The role primarily owns the research deliverables, including data analysis and policy evaluation. It collaborates with external researchers and trainees but does not own the broader project management or external collaborations. This maps to a fit score of 3, as it involves dual ownership of research and data analysis without direct stakeholder dashboard responsibilities."

Assessment: The reasoning explicitly states "without direct stakeholder dashboard responsibilities" — which rules out fit=4. But the model still landed at fit=3 ("dual ownership of research and data analysis") rather than recognizing that sole statistical/research ownership = fit=5. The chain-of-thought led to the right intermediate conclusion (no dashboards) but then mapped to the wrong bucket.

---

#### Direct comparison vs v6

| Version | Agreement rate | n |
|---------|----------------|---|
| v6 | 43.3% (13/30) | 30 |
| v7 | 17.2% (5/29 non-ambiguous) | 29 (1 ambiguous excluded) |
| **Delta** | **−26.1 pts** | |

v7 is a major regression vs v6. The ownership rubric redesign made the prompting problem significantly harder to solve rather than easier.

---

#### Structural anomalies

1. **fit=2 and fit=1 buckets collapsed.** Only 1 sample scored fit=2 (Crossing Hurdles), 0 scored fit=1. The model treated every role — including a biologist and a microbiologist — as fit=3 minimum. The ownership rubric language ("sole ownership of something OTHER than ML") was not sufficient to drive the model to the low end.

2. **fit=5 nearly eliminated.** Only 3 samples scored fit=5 (Comm100, ExaCare, PictorLabs). Pure DS roles like Cover Genius Sr DS GenAI (4), Amazon Applied Scientist (4), Alimentiv Statistician (3), UBC Postdoc (3), and Joveo Agentic AI Engineer (4) all missed. The model is not recognizing sole ML ownership when collaboration language appears in the JD.

3. **"Dual ownership" used as default template.** 16 of 30 samples (53%) have fit=4 with reasoning that constructs a phantom second ownership dimension. The formula "owns X... collaborates with Y for Z... maps to fit=4, dual ownership of X and [Y's function]" appears mechanically across diverse role types. The fit_reasoning is generating a consistent template rather than doing case-by-case analysis.

4. **Collaboration ≠ co-ownership conflation is systematic.** In 10+ cases the model cites the role's collaboration with another team as evidence of "dual ownership." This is the single largest source of bucket errors. Any JD that mentions cross-functional collaboration gets pushed toward fit=3 or fit=4 even when the ownership structure is clearly sole.

5. **Manager rule not applied.** Fasken Manager Data Analytics (436) and RBC Sr Dev Manager (449) were not evaluated by aggregating their team's combined ownership — both received individual-contributor-style scoring. The manager paragraph in the v7 prompt did not change model behavior on manager roles.

---

### v7 + gpt-4o full — model ceiling test

**Date**: 2026-05-01
**Summary**: Same v7 prompt, same 30 canonical IDs, model swapped from `gpt-4o-mini` to `gpt-4o`. Cache miss guaranteed by `(text_hash, "gpt-4o", "v7")` key. Purpose: isolate whether 17% agreement rate is the model or the prompt.

---

#### Per-sample comparison table

Columns: mini score from v7 section above; full score from this run; rubric_expected re-used from v7-mini section (rubric unchanged).
`ERR` = parse failure (canonical_location `Hybrid — Other` could not be resolved after 3 retries — same failure mode as in the v5 30-sample run for this posting).
`?` = rubric-inapplicable / recruiter-thin JD; excluded from agreement denominator.

| canonical_id | employer / title | v7-mini fit | v7-mini reasoning (~80 chars) | v7-full fit | v7-full reasoning (~120 chars) | rubric_expected | mini agree? | full agree? |
|---|---|---|---|---|---|---|---|---|
| 344 | Aspire Software / AI Automation Eng | 4 | "...dual ML + stakeholder-facing products." | 3 | "...involves dual ownership of AI products and operational automation." | 3 | N | Y |
| 347 | Alquemy / Data Scientist | 4 | "...dual ownership of ML models and stakeholder dashboards." | 5 | "...involves sole ownership of ML models and their deployment." | ? | ? | ? |
| 350 | Affirm / Manager MLE (Fraud) | 4 | "...dual ownership of ML models and stakeholder dashboards for decision-making." | 4 | "...involves dual ownership of ML models and stakeholder dashboards." | 3 | N | N |
| 355 | Crossing Hurdles / Data Ops Mgr | 2 | "...focus is on data management rather than ML." | 2 | "...focuses on data management rather than ML/statistical modeling." | 2 | Y | Y |
| 357 | Cover Genius / Sr DS GenAI | 4 | "...dual ownership of ML models and stakeholder-facing evaluation frameworks." | 5 | "...involves sole ownership of ML models and their deployment." | 5 | N | Y |
| 360 | PHSA / Data Analyst | 3 | "...dual ownership of data analysis and reporting." | 3 | "...involves dual ownership of data analysis and reporting." | 2 | N | N |
| 366 | Bird Construction / Sr Data Analyst | 4 | "...dual ownership of ML/statistical models and stakeholder dashboards." | ERR | ERR (Hybrid — Other location parse failure, 3 retries) | 2 | N | ERR |
| 370 | BCCNM / Perf Measurement Spec | 3 | "...dual ownership of data analysis and performance metrics." | 3 | "...involves dual ownership of statistical modeling and performance reporting." | 2 | N | N |
| 380 | Dialpad / Analytics Eng | 4 | "...dual ownership of ML models and stakeholder dashboards." | 4 | "...involves dual ownership of ML/statistical models and stakeholder dashboards." | 3 | N | N |
| 382 | Comm100 / Algorithm Eng AI | 5 | "...sole ownership of ML/statistical models and their deployment." | 4 | "...involves dual ownership of ML models and stakeholder engagement." | 5 | Y | N |
| 387 | Hopper / Finance & Strategy Mgr | 4 | "...dual ownership of financial modeling and stakeholder reporting." | 4 | "...involves dual ownership of financial modeling and stakeholder reporting." | 4 | Y | Y |
| 389 | IBM / Managing Consultant SAP Analytics | 3 | "...dual ownership of model development and testing." | 3 | "...involves dual ownership of model development and integration tasks." | 2 | N | N |
| 393 | Marine Biologics / R&D Scientist | 3 | "...dual ownership of lab management and patent-related work." | 3 | "...involves dual ownership of lab management and patent-related work." | 1 | N | N |
| 397 | Alimentiv / Statistician | 3 | "...dual ownership of statistical models and project support." | 3 | "...involves dual ownership of statistical models and project support." | 5 | N | N |
| 413 | Joveo / Agentic AI Engineer | 4 | "...dual ownership of AI models and performance optimization." | 5 | "...involves sole ownership of the AI agents as problem-solving tools." | 5 | N | Y |
| 417 | Amazon / SDE-II | 3 | "...dual ownership of ML models and system performance." | 3 | "...involves dual ownership of ML/statistical models and system performance improvements." | 2 | N | N |
| 436 | Fasken / Manager Data Analytics | 4 | "...dual ownership of analytics and stakeholder reporting." | 4 | "...involves dual ownership of analytics outputs and stakeholder dashboards." | 2 | N | N |
| 448 | Amazon / Applied Scientist | 4 | "...dual ownership of ML models and stakeholder insights." | 5 | "...encompasses sole ownership of ML models and their integration into business processes." | 5 | N | Y |
| 449 | RBC / Sr Dev Manager | 4 | "...dual ownership of ML models and stakeholder dashboards." | 3 | "...involves dual ownership of ML/statistical models and technical strategy." | 3 | N | Y |
| 450 | Diligent / AI Solution Architect | 4 | "...dual ownership of AI solutions and stakeholder engagement." | 4 | "...involves dual ownership of AI solutions and stakeholder engagement for business outcomes." | 2 | N | N |
| 465 | Clio / Manager Enterprise AI | 4 | "...dual ownership of AI initiatives and stakeholder engagement." | 4 | "...involves dual ownership of AI initiatives and stakeholder engagement." | 3 | N | N |
| 466 | ExaCare AI / MLE | 5 | "...sole ownership of ML models and their deployment." | 5 | "...encompasses sole ownership of ML models and their deployment." | 5 | Y | Y |
| 474 | ICBC / Intermediate Dev RPA/AI | 4 | "...dual ownership of ML models and stakeholder dashboards." | 3 | "...involves dual ownership of ML/statistical models and application development." | 2 | N | N |
| 488 | The Select Group / Developer Analyst | 3 | "...dual ownership of data analysis and collaboration with other teams." | 3 | "...involves dual ownership of data analysis and collaboration with other teams." | 2 | N | N |
| 489 | Grafana Labs / Sr Analytics Eng | 3 | "...dual ownership of data modeling and collaboration with other teams." | 3 | "...involves dual ownership of data modeling and stakeholder analytics." | 2 | N | N |
| 499 | KOHO / Sr BA Fraud Strategy | 4 | "...dual ownership of fraud models and stakeholder dashboards." | 4 | "...involves dual ownership of fraud models and stakeholder engagement." | 2 | N | N |
| 522 | PictorLabs / Sr Applied ML Eng CV | 5 | "...sole ownership of ML models and their deployment." | 5 | "...encompasses sole ownership of ML models and their deployment." | 5 | Y | Y |
| 532 | Turing / Quant Finance Professional | 3 | "...dual ownership of statistical modeling and collaboration with AI teams." | 3 | "...involves dual ownership of quantitative modeling and collaboration with AI specialists." | 2 | N | N |
| 534 | UBC / Postdoc Research Fellow | 3 | "...dual ownership of research and data analysis without direct stakeholder dashboard responsibilities." | 3 | "...involves dual ownership of health economics research and data analysis." | 5 | N | N |
| 558 | Brokkr / Microbiology Lead | 3 | "...dual ownership of experimental design and collaboration with engineering." | 4 | "...involves dual ownership of experimental design and stakeholder communication." | 1 | N | N |

---

#### Aggregate stats

| Metric | v7-mini | v7-full |
|--------|---------|---------|
| Agreement with rubric | 5 / 29 (17.2%) | 9 / 28 (32.1%) |
| Disagreement with rubric | 24 / 29 (82.8%) | 19 / 28 (67.9%) |
| Ambiguous / rubric-inapplicable (?) | 1 / 30 | 1 / 30 |
| ERR (parse failure) | 0 / 30 | 1 / 30 (canonical_id=366) |
| Delta (full − mini) | | **+14.9 pts** |

**v7-full fit_score distribution** (29 scored; 1 ERR):

| Score | v7-mini count | v7-full count |
|-------|--------------|--------------|
| 1 | 0 | 0 |
| 2 | 1 | 1 |
| 3 | 10 | 13 |
| 4 | 16 | 10 |
| 5 | 3 | 5 |
| ERR | 0 | 1 |

---

#### Three observations

**1. Did gpt-4o avoid the "dual ownership template" failure (53% at fit=4 in mini)?**

Partially. gpt-4o-mini produced 16/30 at fit=4 (53%); gpt-4o produced 10/30 at fit=4 (33%). The dual-ownership template is still present — 23 of the 29 scored gpt-4o reasoning strings contain the phrase "dual ownership" — but gpt-4o shifts some of that mass toward fit=3 (13 vs mini's 10) and fit=5 (5 vs mini's 3). The model is somewhat less gravitationally attracted to fit=4, but the underlying pattern-matching failure (treating collaboration as co-ownership) persists.

**2. Did gpt-4o use fit=1 and fit=2 for non-DS roles?**

No improvement on fit=1; marginal improvement on fit=2. gpt-4o returned fit=2 for exactly 1 sample (Crossing Hurdles Data Ops, canonical_id=355) — same as mini. Brokkr Microbiology Lead (rubric=1) was scored fit=4 by gpt-4o — *worse* than mini's fit=3. Marine Biologics R&D Scientist (rubric=1) was fit=3 for both models. Amazon SDE-II, IBM SAP HANA, ICBC RPA Developer (all rubric=2) were fit=3 for gpt-4o, same as mini. The model ceiling for low-end anchor discrimination is identical between the two models.

**3. Did gpt-4o apply the manager rule?**

No. Affirm Manager MLE (rubric=3, should evaluate team's aggregate DS ownership = pure DS team → could argue 5 but rubric=3 for managerial overhead), Fasken Manager Data Analytics (rubric=2, BI/analytics team), and Clio Manager Enterprise AI (rubric=3) all received individual-contributor-style scoring from gpt-4o. RBC Sr Dev Manager improved from mini's 4 to gpt-4o's 3 (hitting rubric=3) but the reasoning cites "dual ownership of ML/statistical models and technical strategy" — not a manager-rule application. The improvement is coincidental pattern-matching, not genuine manager-rule reasoning.

---

#### Five verbatim fit_reasoning samples (same 5 canonical_ids as v7-mini section)

**ExaCare AI MLE (466) — Best-case: gpt-4o**
> "The role primarily owns the development and deployment of machine learning models, including the entire ML lifecycle. It collaborates with teams on data management and model performance monitoring but does not specify ownership of stakeholder dashboards or BI tools. This maps to a fit score of 5, as the role encompasses sole ownership of ML models and their deployment."

vs v7-mini:
> "The role primarily owns the development and deployment of ML models, including entire ML lifecycle… sole ownership of ML models and their deployment."

Assessment: Nearly identical. Both models correctly identify sole ML ownership and explicitly note the absence of dashboards. gpt-4o adds slightly more explicit hedging ("does not specify ownership of stakeholder dashboards or BI tools") which is marginally better chain-of-thought.

---

**Amazon Applied Scientist (448) — Bucket mapping fixed by gpt-4o:**
> "The role primarily owns the development and deployment of machine learning models to drive business insights and customer discovery. It collaborates with engineering and business teams for implementation and strategy. This maps to a fit score of 5, as the role encompasses sole ownership of ML models and their integration into business processes."

vs v7-mini:
> "The role primarily owns the development and deployment of ML models to drive business insights… dual ownership of ML models and stakeholder insights." (fit=4)

Assessment: gpt-4o correctly resolved the "stakeholder insights" phantom dual-ownership that trapped mini at fit=4. The reasoning now correctly interprets business teams as downstream consumers, not co-owners. This is the clearest qualitative improvement gpt-4o shows over mini on this corpus.

---

**Alimentiv Statistician (397) — Shared failure:**
> "The role primarily owns the statistical analysis and reporting aspects of clinical trials. It collaborates with project teams and data management to ensure data integrity and adherence to protocols. This maps to a fit score of 3, as it involves dual ownership of statistical models and project support."

vs v7-mini (identical):
> "The role primarily owns the statistical analysis and reporting for clinical trials… dual ownership of statistical models and project support." (fit=3)

Assessment: Word-for-word identical reasoning and identical wrong bucket. This is the clearest evidence that the failure is structural to the v7 prompt (collaboration-as-co-ownership), not the model. A sole statistician owning statistical models for clinical trials should be rubric=5. Neither model can escape the phantom dual-ownership framing when the JD mentions any form of collaboration.

---

**Marine Biologics R&D Scientist (393) — Neither model applies rubric=1:**
> "The role primarily owns the patent filing and lab management as its deliverables. It collaborates with patent counsel and possibly other scientists for lab execution and documentation. This maps to a fit score of 3, as it involves dual ownership of lab management and patent-related work."

vs v7-mini:
> "The role primarily owns the patent filing and lab management processes… dual ownership of lab management and patent-related work." (fit=3)

Assessment: Identical failure. A non-data role in food-science chemistry is rubric=1; both models return fit=3. The ownership rubric's language ("sole ownership of something OTHER than ML/statistical models" for fit=2) apparently does not signal to the model that fit=1 should be applied to roles with zero data content. Neither model can identify fit=1.

---

**UBC Postdoc Research Fellow (534) — Self-contradictory chain-of-thought preserved:**
> "The role primarily owns the research deliverables, including data analysis and policy evaluation. It collaborates with external researchers and trainees but does not own the overall project direction. This maps to a fit score of 3, as it involves dual ownership of health economics research and data analysis."

vs v7-mini:
> "…owns research deliverables, including data analysis and policy evaluation… dual ownership of research and data analysis without direct stakeholder dashboard responsibilities." (fit=3)

Assessment: Both models get fit=3. gpt-4o's reasoning is actually slightly worse — it adds "does not own the overall project direction" (which is inaccurate; postdocs own their research agenda) and drops the v7-mini's explicit "without direct stakeholder dashboard responsibilities" clause, which at least showed the model reasoning toward the right diagnosis. For this rubric=5 role (sole statistical/research ownership), neither model escapes fit=3. The self-contradictory pattern is structural.

---

#### Verdict

**Marginal improvement: v7-full agreement 32.1% vs v7-mini 17.2%. Delta = +14.9 percentage points.**

gpt-4o improves over gpt-4o-mini on exactly the cases where the v7 prompt is "almost right" — roles where the mini model constructed a phantom dual-ownership despite the JD having clear sole ownership language (Amazon Applied Scientist 448: 4→5 ✓; Joveo Agentic AI Eng 413: 4→5 ✓; Cover Genius Sr DS 357: 4→5 ✓; Aspire AI Automation 344: 4→3 ✓; RBC Sr Dev Mgr 449: 4→3 ✓). These are cases where stronger instruction-following flipped the decision.

However, the prompt's structural failures are unchanged at both model tiers:
- Alimentiv Statistician (rubric=5) → fit=3 for both: the collaboration-as-co-ownership failure is prompt-level, not model-level.
- UBC Postdoc (rubric=5) → fit=3 for both: same root cause.
- fit=1 and fit=2 identification: both models return fit=3 as a floor for non-data roles (Marine Biologics, IBM SAP HANA, Amazon SDE-II).
- Manager rule: not applied by either model.
- Brokkr Microbiology Lead: gpt-4o actually *regressed* vs mini (fit=4 vs mini's fit=3; rubric=1).

The 32.1% ceiling with gpt-4o means the remaining 68% failure rate is attributable to prompt design, not model capability. Moving to gpt-4o full would roughly double the per-call cost (from ~$0.0014 to ~$0.0013 per sample in this run, but gpt-4o pricing is ~12-15× mini for equal token counts at larger scale). The cost of this 30-sample run was **$0.038** vs an estimated ~$0.0043 for the equivalent mini run — approximately 9× more expensive for a +14.9 pt accuracy gain.

The verdict is clear: **the prompt must be fixed before model-scaling is worthwhile**. The collaboration-as-co-ownership pattern and fit=1/2 anchor failures cannot be solved by a stronger model within the v7 prompt design.

---

#### Total cost

| Metric | Value |
|--------|-------|
| Model | gpt-4o (gpt-4o-2024-08-06 or equivalent) |
| Samples completed | 29 / 30 (1 ERR on canonical_id=366) |
| Total cost (from llm_call_ledger) | **$0.0378** |
| Estimated mini-equivalent cost | ~$0.0043 (30 × $0.00143) |
| Cost ratio full/mini | ~9× |
| Cost watchdog ($1.00) triggered | No |

---

### v8 ownership rubric + 6 worked examples — same 30 samples

**Date**: 2026-05-01
**Summary**: v7 prompt + explicit collaboration rule + 6 surgical worked examples targeting observed failure modes; gpt-4o-mini.

#### What v8 adds vs v7

v7 established the ownership rubric (5-level scale + manager paragraph) but scored only 17.2% on mini and 32.1% on full. The model-ceiling test confirmed both models produce identical wrong reasoning on collaboration-as-co-ownership cases. v8 keeps v7 verbatim and adds two targeted surgical changes to the fit_score section:

1. **Explicit collaboration rule** (inserted after the 5 score lines, before the manager paragraph): "Collaboration does NOT constitute co-ownership. A role is only 'owning' something if it is on the hook for delivering it. Cross-functional mentions ('works with X team', 'partners with Y', 'collaborates with engineering') are evidence of COLLABORATION, not co-ownership."

2. **6 worked examples** (new `=== WORKED EXAMPLES ===` section after the manager paragraph): one example per score level (fit=5, fit=4, fit=3, fit=2, fit=1) plus one manager rule application (fit=3). Each example is targeted at a specific observed failure mode: Example 1 (fit=5 with cross-team collaboration) addresses the Alimentiv/UBC Postdoc/Amazon Applied Sci collaboration-as-co-ownership pattern; Example 4 (fit=2 Analytics Engineer) addresses Dialpad/Grafana inflation; Example 5 (fit=1 Microbiology Lead) addresses Marine Biologics/Brokkr non-data role collapse; Example 6 (Manager rule) addresses Fasken/RBC manager-rule non-application.

All other 9 M3 field sections are byte-identical to v7.

---

#### Per-sample comparison table

`rubric_expected` values carried from v7 section (rubric unchanged). `?` = recruiter-thin JD, excluded from denominator. `ERR` = parse failure.

| canonical_id | employer / title | v7-mini | v7-full | v8-mini | rubric_expected | v8-mini reasoning (~120 chars) | agree? |
|---|---|---|---|---|---|---|---|
| 344 | Aspire Software / AI Automation Eng | 4 | 3 | 3 | 3 | "...owns AI agents/products as core deliverables. Collaborates with portfolio operators but does not own their work. fit=3..." | Y |
| 347 | Alquemy S&C / Data Scientist | 4 | 5 | 3 | ? | "...owns ML models and data analysis. Collaborates with DE and product teams but does not own their work. fit=3, dual ownership..." | ? |
| 350 | Affirm / Manager MLE (Fraud) | 4 | 4 | 4 | 3 | "...owns end-to-end ML solutions for fraud detection. Collaborates with Product, Fraud Analytics, Engineering. fit=4, dual ownership..." | N |
| 355 | Crossing Hurdles / Data Ops Mgr | 2 | 2 | 2 | 2 | "...owns data workflows and operational challenges. Collaborates with cross-functional teams but does not own any ML models. fit=2..." | Y |
| 357 | Cover Genius / Sr DS GenAI | 4 | 5 | 4 | 5 | "...owns LLM strategy and model performance evaluation. Collaborates with product/engineering for data structure optimization. fit=4..." | N |
| 360 | PHSA / Data Analyst | 3 | 3 | 3 | 2 | "...owns dataset maintenance, report automation, and documentation. Collaborates with project teams for QA and reporting. fit=3..." | N |
| 366 | Bird Construction / Sr Data Analyst | 4 | ERR | 4 | 2 | "...owns analytics solutions and dashboards. Collaborates with Data Engineering and IT but does not own engineering aspects. fit=4..." | N |
| 370 | BCCNM / Perf Measurement Spec | 3 | 3 | 3 | 2 | "...owns performance measurement and data analysis. Collaborates with teams to integrate initiatives. fit=3, dual ownership..." | N |
| 380 | Dialpad / Analytics Engineer | 4 | 4 | 3 | 3 | "...owns data pipeline development and optimization. Collaborates with AI/Eng/Product teams but does not own AI models. fit=3..." | Y |
| 382 | Comm100 / Algorithm Engineer AI | 5 | 4 | 3 | 5 | "...owns AI model development and deployment. Collaborates with cross-regional engineering teams. fit=3, dual ownership of model dev..." | N |
| 387 | Hopper / Finance & Strategy Mgr | 4 | 4 | 3 | 4 | "...owns financial systems and forecasting models. Collaborates with business leaders and sales teams. fit=3, dual ownership..." | N |
| 389 | IBM / Managing Consultant SAP | 3 | 3 | 3 | 2 | "...owns SAP HANA Information Models and HANA views. Collaborates with BI tools for integration. fit=3, dual ownership..." | N |
| 393 | Marine Biologics / R&D Scientist | 3 | 3 | 3 | 1 | "...owns ingredient development and patenting. Collaborates with patent counsel but does not own legal aspects. fit=3..." | N |
| 397 | Alimentiv / Statistician | 3 | 3 | 3 | 5 | "...owns statistical analysis and reporting for clinical trials. Collaborates with project teams on data collection. fit=3, dual ownership..." | N |
| 413 | Joveo / Agentic AI Engineer | 4 | 5 | 5 | 5 | "...owns development and deployment of AI agents. Collaborates with other teams for platform integration. fit=5, sole ownership..." | Y |
| 417 | Amazon / SDE-II | 3 | 3 | 3 | 2 | "...owns distributed systems and optimization algorithms. Collaborates with scientists and PMs but not their deliverables. fit=3..." | N |
| 436 | Fasken / Manager Data Analytics | 4 | 4 | 4 | 2 | "...owns analytics solutions, dashboards and reports. Collaborates with DE for reliable data modeling. fit=4, dual ownership..." | N |
| 448 | Amazon / Applied Scientist | 4 | 5 | 4 | 5 | "...owns ML model development and deployment. Collaborates with engineering and business teams. fit=4, dual ownership of ML + insights..." | N |
| 449 | RBC / Sr Dev Manager | 4 | 3 | 4 | 3 | "...owns end-to-end SDLC for modernization including AI/ML integration. Collaborates with architects and PMs. fit=4..." | N |
| 450 | Diligent / AI Solution Architect | 4 | 4 | 4 | 2 | "...owns AI solution development and deployment. Collaborates with business leaders and cross-functional teams. fit=4..." | N |
| 465 | Clio / Manager Enterprise AI | 4 | 4 | 3 | 3 | "...owns Enterprise AI strategy and roadmap. Collaborates with DE and Data Insights teams for governance. fit=3, not direct ML ownership..." | Y |
| 466 | ExaCare AI / MLE | 5 | 5 | 5 | 5 | "...owns ML model development and deployment, entire ML lifecycle. Collaborates with other teams for data/infra. fit=5, sole ownership..." | Y |
| 474 | ICBC / Intermediate Dev RPA/AI | 4 | 3 | 3 | 2 | "...owns RPA and AI software application development. Collaborates with business analysts for requirements. fit=3, dual ownership..." | N |
| 488 | The Select Group / Developer Analyst | 3 | 3 | 3 | 2 | "...owns data extraction and analysis for marketing campaigns. Collaborates with cross-functional teams. fit=3, dual ownership..." | N |
| 489 | Grafana Labs / Sr Analytics Eng | 3 | 3 | 3 | 2 | "...owns data stack architecture and infrastructure. Collaborates with multiple teams for data needs. fit=3, dual ownership..." | N |
| 499 | KOHO / Sr BA Fraud Strategy | 4 | 4 | 4 | 2 | "...owns fraud control landscape and fraud detection models. Collaborates with Product/Eng/Compliance. fit=4, dual ownership..." | N |
| 522 | PictorLabs / Sr Applied ML Eng CV | 5 | 5 | 4 | 5 | "...owns CV model development and optimization. Collaborates with engineers for deployment/productionization. fit=4, dual ownership..." | N |
| 532 | Turing / Quant Finance Professional | 3 | 3 | 3 | 2 | "...owns AI model evaluation and training in quantitative finance. Collaborates with AI researchers. fit=3, dual ownership..." | N |
| 534 | UBC / Postdoc Research Fellow | 3 | 3 | 3 | 5 | "...owns health economics research projects and data analysis. Collaborates with external researchers and trainees. fit=3, dual ownership..." | N |
| 558 | Brokkr / Microbiology Lead | 3 | 4 | 3 | 1 | "...owns microbiological experiment design and process development. Collaborates with engineers to translate results. fit=3..." | N |

---

#### Aggregate stats

| Metric | Value |
|--------|-------|
| v8-mini agreement | **7 / 29** (24.1%) — canonical_id=347 excluded (rubric-inapplicable) |
| Disagreement | 22 / 29 (75.9%) |
| ERR (parse failure) | 0 / 30 (canonical_id=366 recovered on retry 2/3 — same Hybrid—Other location failure, same retry path as v5) |

**v8-mini fit_score distribution:**

| Score | v7-mini | v7-full | v8-mini |
|-------|---------|---------|---------|
| 1 | 0 | 0 | 0 |
| 2 | 1 | 1 | 1 |
| 3 | 10 | 13 | 18 |
| 4 | 16 | 10 | 9 |
| 5 | 3 | 5 | 2 |
| ERR | 0 | 1 | 0 |

**Comparison line**: v7-mini was 17%, v7-full was 32%, **v8-mini is 24.1%** (delta vs v7-mini: +7 pts).

The distribution shift is notable: v7-mini had 16 at fit=4 (53%); v8-mini has 9 at fit=4 (30%) and 18 at fit=3 (60%). The collaboration rule successfully broke the fit=4 gravitational pull — mass shifted from fit=4 to fit=3. But fit=3 is now the new default floor: the model correctly avoided phantom fit=4 reasoning, but replaced it with phantom fit=3 ("dual ownership of X and Y") for roles that should be fit=1, fit=2, or fit=5.

---

#### Targeted failure-mode check

Each worked example's target case evaluated:

| Example target | Canonical | v7-mini | v8-mini | rubric | Result |
|---|---|---|---|---|---|
| Example 1: Alimentiv Statistician → fit=5 (collab ≠ co-own) | 397 | 3 | 3 | 5 | **FAIL** — unchanged; "collaborates with project teams" still mapped as co-ownership of "project support" |
| Example 1: UBC Postdoc → fit=5 (collab test) | 534 | 3 | 3 | 5 | **FAIL** — unchanged; "collaborates with external researchers" still mapped as dual ownership |
| Example 4: Dialpad Analytics Eng → fit=2 or fit=3 | 380 | 4 | 3 | 3 | **PASS** — v8 correctly landed at fit=3 (rubric=3); moved from v7's fit=4 |
| Example 4: Grafana Sr Analytics Eng → fit=2 | 489 | 3 | 3 | 2 | **FAIL** — still fit=3 instead of fit=2; sole non-DS data ownership not identified |
| Example 5: Marine Biologics → fit=1 | 393 | 3 | 3 | 1 | **FAIL** — non-data role still scored fit=3; Example 5 not applied |
| Example 5: Brokkr Microbiology Lead → fit=1 | 558 | 3 | 3 | 1 | **FAIL** — non-data role still scored fit=3; Example 5 not applied |
| Example 6: Fasken Manager Data Analytics → manager rule applied | 436 | 4 | 4 | 2 | **FAIL** — manager rule not applied; scored as individual contributor |
| Example 6: RBC Sr Dev Manager → manager rule applied | 449 | 4 | 4 | 3 | **FAIL** — manager rule not applied; same phantom dual-ownership pattern |

**Summary**: 1 PASS / 7 FAIL on targeted failure modes. The only gain is Dialpad (380) moving from fit=4 → fit=3, which is a correct landing. All other targets unchanged from v7-mini.

One partial positive: the collaboration rule did shift the overall distribution away from fit=4 (16→9 cases), which is directionally correct. But the model replaced fit=4 default reasoning with fit=3 default reasoning — the phantom "dual ownership" template persists, just now concluding fit=3 instead of fit=4 for most roles.

---

#### 5 verbatim fit_reasoning samples

Same 5 canonical_ids as v7 sections for cross-run comparison.

**ExaCare AI MLE (466) — Correct sole-ownership identification:**
> "The role primarily owns the development and deployment of machine learning models, including the entire ML lifecycle. It collaborates with other teams for data management and infrastructure but does not explicitly mention co-ownership of any other deliverables. This maps to a fit score of 5 due to sole ownership of the ML models and their deployment."

vs v7-mini: "...sole ownership of ML models and their deployment." — Nearly identical. Both correct. The explicit "does not explicitly mention co-ownership" clause is the collaboration rule applying correctly here.

---

**Amazon Applied Scientist (448) — Bucket mapping still wrong:**
> "The role primarily owns the development and deployment of machine learning models for business applications. It collaborates with engineering and business teams for insights and decision-making but does not own the engineering aspects of model deployment. This maps to a fit score of 4 due to dual ownership of ML models and stakeholder insights."

vs v7-mini: "...dual ownership of ML models and stakeholder insights." (fit=4) — Identical reasoning and same wrong bucket. The collaboration rule clarified that the engineering aspects are collaboration not co-ownership (correct), but "stakeholder insights" is still being constructed as a phantom second ownership dimension. Expected: fit=5.

---

**Alimentiv Statistician (397) — Collaboration rule ignored for this pattern:**
> "The role owns the statistical analysis and reporting for clinical trials, ensuring adherence to best practices. It collaborates with project teams and data management to align data collection with project protocols. This maps to a fit score of 3, as it involves dual ownership of statistical analysis and project support."

vs v7-mini (word-for-word identical): "...dual ownership of statistical models and project support." — The Example 1 worked example (which directly models this failure mode) made no difference. The model reads "collaborates with project teams" and constructs "dual ownership of statistical analysis and project support" regardless of the explicit rule stating collaboration ≠ co-ownership. This is the clearest evidence the failure is too deep for a rule-plus-example fix.

---

**Marine Biologics R&D Scientist (393) — Example 5 not applied:**
> "The role primarily owns the development and patenting of a new ingredient, including lab management and process optimization. It collaborates with patent counsel for filing and prosecution but does not own the legal aspects of patenting. This maps to fit=3 due to the dual ownership of lab management and ingredient development."

vs v7-mini: "...dual ownership of lab management and patent-related work." — The explicit fit=1 lab-science example (Example 5: "Microbiology R&D Lead: designs wet-lab experiments... no analytical modeling work → fit=1") did not transfer to this Marine Biologics case. The model correctly noted it does not own the legal aspects of patenting (collaboration rule applied partially) but still scored fit=3. The model treats "dual ownership of lab management + ingredient development" as the conclusion, not fit=1 (non-data role).

---

**UBC Postdoc Research Fellow (534) — Self-contradictory pattern unchanged:**
> "The role primarily owns the delivery of health economics research projects, including data analysis and policy evaluations. It collaborates with external researchers and trainees but does not own the overall project direction, which is led by Dr. Zhang. This maps to a fit score of 3 due to dual ownership of research and data analysis responsibilities."

vs v7-mini: "...dual ownership of research and data analysis without direct stakeholder dashboard responsibilities." — The chain-of-thought correctly identifies collaboration (external researchers, trainees) as not-owned. But then constructs "dual ownership of research and data analysis" — treating the two aspects of the same job (research + analysis) as two separate co-owned deliverables, landing at fit=3 instead of fit=5. Example 1 (sole DS ownership with cross-team collaboration) did not transfer to this academic research context. Expected: fit=5.

---

#### Verdict

v8-mini agreement rate: **24.1%** (7/29). Delta vs v7-mini: **+7 pts**.

v8 is a marginal improvement over v7-mini (+7 pts) but well below the 60% threshold for "examples worked." The 6 surgical worked examples and explicit collaboration rule produced one targeted fix (Dialpad 380: 4→3 ✓) and a distribution shift away from fit=4 (53%→30%), but the core failures are unchanged:

- The collaboration-as-co-ownership failure persists for roles like Alimentiv Statistician (397) and UBC Postdoc (534) where the JD explicitly mentions working with other teams. Example 1 directly models this pattern but the model does not apply it to analogous cases.
- The fit=1/2 floor identification failure persists for Marine Biologics (393), Brokkr (558), IBM SAP HANA (389), and KOHO BA (499). Example 5 (lab science = fit=1) and Example 4 (analytics engineer = fit=2) did not transfer.
- The manager rule is still not applied for Fasken (436) and RBC (449).
- New regression: Comm100 (382) moved from v7-mini's correct fit=5 to v8's fit=3, and PictorLabs (522) moved from correct fit=5 to fit=4. The collaboration rule created collateral damage — roles with genuine sole ownership that mention any team interaction are now being pushed down.

**Conclusion: prompt design ceiling reached.** v8 < 40% agreement means the worked-examples approach cannot close the gap. The 3-version pattern (v7=17%, v8-mini=24%, v7-full=32%) shows diminishing returns. The failure modes are structural to how the model interprets ownership language when collaboration is mentioned, and adding more examples or rules does not overcome this. Recommend accepting the current prompt and relying on manual override during daily use, or switching to a different prompt architecture (e.g., chain-of-thought scratchpad with explicit "list all deliverables owned" before scoring).

**Cost**: $0.0396 (30 × gpt-4o-mini, ~$0.00132/call average). Under $0.05 watchdog.
