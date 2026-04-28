# Quality Log — TASK-M2-006 — LLM Extraction (C18)

**Date**: 2026-04-27
**Agent**: data-pipeline
**Task**: LLM Extraction (C18) — strict canonical labels

---

## Spec Tension Resolution: Location Enum + "Other" Fallback

**The tension**: AC #2 requires strict Pydantic `Literal` enum enforcement for `canonical_location`. TDD §C18 says location "MAY be returned verbatim as a fallback (rare — flagged in quality review)". The real DB has postings from Burnaby, Waterloo, Kelowna, Richmond — none in the TDD-enumerated city list. Strict Literal without a fallback would cause infinite retry loops on these valid postings.

**Resolution**: `"Other"` is added as a permitted value in the `CanonicalLocation` Literal. This satisfies AC #2 (strict Pydantic Literal — validation passes only for known values including "Other") AND TDD §C18 (rare cities fall back gracefully without retrying infinitely).

The prompt's metro-area aliasing rules map the most common BC suburbs (Burnaby, Richmond, Surrey, Coquitlam) to "Vancouver" and GTA suburbs to "Toronto", reducing "Other" hits to genuinely rare cases (cities like Prince George, Saskatoon, etc.).

---

## Acceptance Criteria Verdicts

| AC | Description | Result |
|----|-------------|--------|
| AC #1 | `extract_canonical(posting)` takes `full_jd` + optional priors; returns `CanonicalExtraction` | **PASS** |
| AC #2 | Strict enums for seniority + location (out-of-enum = parse failure → retry) | **PASS** — Pydantic Literal enforces both; parse-failure retry loop verified by 3 test cases |
| AC #3 | `canonical_company` normalized — no Inc/Ltd suffixes, 5 test cases | **PASS** — 6 test cases: Inc., Ltd, Canada Inc., Corp., Limited, no-suffix |
| AC #4 | `team_or_department` 2-5 words, org-unit only | **PASS** — field_validator warns on out-of-range; None accepted |
| AC #5 | Cache by SHA256(full_jd) — second call hits cache (mock count = 1) | **PASS** — in-process + DB cache both verified |
| AC #6 | `llm_call_ledger` row written per call with cost | **PASS** — success + cache_hit + retry rows all verified |
| AC #7 | Retry on transient errors (3 attempts, exponential backoff) | **PASS** — RateLimitError + ProviderUnavailableError both tested; 3-retry exhaustion raises |
| AC #8 | 10 synthetic JDs all extract within enum constraints | **PASS** — all 10 pass; seniority and location values validated against Literal |
| AC #9 | Live test (one real posting): all canonical fields populated and valid | **PASS** — see Live Test Results below |

**Overall: 9/9 PASS**

---

## Pytest Summary

```
SKIP_LIVE=1 .venv/bin/python -m pytest tests/llm/test_extract.py -v
39 passed, 1 skipped, 0 failed

Full suite:
669 passed, 2 skipped, 31 warnings, 0 failed
```

The 2 skipped tests are: the live extraction test (SKIP_LIVE=1) and one pre-existing auth skip.

---

## Live Test Results (AC #9)

**Posting ID**: 91
**Company (email-parsed)**: TELUS Digital
**JD length**: 3,227 characters

**CanonicalExtraction output**:
```json
{
  "canonical_title": "Personalized Internet Assessor",
  "canonical_company": "TELUS",
  "canonical_seniority": "Junior",
  "canonical_location": "Remote — Canada",
  "team_or_department": "AI Community",
  "top_skills": [
    "Persian",
    "English",
    "Internet Research",
    "Feedback Analysis",
    "Communication"
  ],
  "role_summary": "The Personalized Internet Assessor will analyze and provide feedback on various types of information for search engines. This part-time freelance role requires excellent communication skills in Persian and English. The assessor will help improve user experience by reviewing and rating search results for relevance and quality. No previous professional experience is required, but candidates must pass a language assessment and qualification exam."
}
```

**Field validation**:
- `canonical_title`: populated — PASS
- `canonical_company`: "TELUS" (no "Digital" suffix from email parse, no Inc/Ltd) — PASS
- `canonical_seniority`: "Junior" — in enum — PASS
- `canonical_location`: "Remote — Canada" — in enum — PASS
- `team_or_department`: "AI Community" (2 words) — PASS
- `top_skills`: 5 skills, non-empty — PASS
- `role_summary`: 4 sentences, neutral, no marketing language — PASS
- No legal suffix in `canonical_company` — PASS

**Ledger row**:
```
openai | gpt-4o-mini | extraction | 1648 input tokens | 152 output tokens | $0.0003384 | 4574ms | success
```

**Cost**: $0.0003384 (well within <$0.01 target per posting)

**Prompt iterations**: 0 — the extraction was correct on the first attempt.

**Note on company normalization**: The email-parsed company was "TELUS Digital" but the LLM extracted "TELUS" (dropping "Digital" as a division name). This is reasonable — the validator would strip legal suffixes but not division names. The result is acceptable since "TELUS" is the canonical employer. If users prefer "TELUS Digital" to be preserved, the prompt few-shots could be adjusted in a later calibration pass.

---

## Probabilistic Quality Assessment

The extraction quality is evaluated on the live posting above. Per Gate 4, probabilistic results require user approval before M2 milestone closes.

| Field | Value from live test | Assessment |
|-------|---------------------|------------|
| `canonical_company` | "TELUS" (from "TELUS Digital") | Acceptable — TELUS is the parent employer |
| `canonical_seniority` | "Junior" | Correct — the posting is for a part-time freelance role with no experience required |
| `canonical_location` | "Remote — Canada" | Correct — posting says "in Canada" |
| `team_or_department` | "AI Community" | Reasonable — the posting references the "TELUS AI Community" |
| `top_skills` | ["Persian", "English", ...] | Correct for this language-assessment role |
| `role_summary` | 4 neutral sentences | Good quality — captures the role accurately |

**User approval required** before M2 milestone closes per Gate 4.

---

## Cache Behavior

- First call (live test CLI): 1 OpenAI API call → result stored in `extraction_cache` table
- Second call (pytest live test): DB cache hit → 0 API calls, `cache_hit` ledger row written
- Total API cost for this task: $0.0003384 (one live API call)
