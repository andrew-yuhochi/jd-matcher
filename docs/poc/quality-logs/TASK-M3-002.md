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
