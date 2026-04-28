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

---

## Independent Validation (test-validator, 2026-04-27)

**Validator**: test-validator agent
**Commit validated**: `484279f`

### Unit Tests

Full suite: **669 passed, 2 skipped, 0 failed** (matches implementer's claim exactly)
`tests/llm/test_extract.py`: **39 passed, 1 skipped** (live test gated by `SKIP_LIVE=1`)

### Per-AC Verdicts

| AC | Description | Verdict | Evidence |
|----|-------------|---------|----------|
| AC #1 | `extract_canonical(posting)` takes `full_jd` + optional priors; returns `CanonicalExtraction` | **PASS** | `PostingRow` dataclass; `priors: dict[str, str] | None` param; return annotation is `CanonicalExtraction`; mock call exercise confirmed `type: CanonicalExtraction`, seniority and location fields populated |
| AC #2 | Strict enums for seniority + location (Pydantic validation; out-of-enum = parse failure → retry) | **PASS** | `CanonicalSeniority = Literal[...]` (8 values), `CanonicalLocation = Literal[...]` (18 values incl. "Other"); `"Architect"` → `literal_error`; `"Mars"` → `literal_error`; `"Other"` accepted; tests `test_invalid_seniority_raises`, `test_invalid_location_raises`, `test_other_location_accepted` all pass |
| AC #3 | `canonical_company` normalized (no Inc/Ltd suffixes — verified by 5 test cases) | **PASS** | 6 test cases pass: `test_strips_inc`, `test_strips_ltd`, `test_strips_canada_inc`, `test_strips_corp`, `test_strips_limited`, `test_no_suffix_unchanged`; regex covers Inc./Ltd./Limited/Corp./Corporation/Co./LLC/LP variants |
| AC #4 | `team_or_department` canonical (2-5 words, org-unit only — not role-level) | **PASS** | `validate_team_word_count` logs WARNING on out-of-range but does not raise (TDD-consistent: model is prompted to produce correct values; validator warns for telemetry); 3 tests pass: None, 2-word, 5-word cases |
| AC #5 | Cache by `SHA256(full_jd)` hit on second call (mock count = 1) | **PASS** | In-process cache: `provider.extract.call_count == 1` verified live; DB cache: cross-process simulation (`_PROCESS_CACHE.clear()` + provider2 = 0 calls) verified; `extraction_cache` rows = 1 confirmed in temp DB and real DB |
| AC #6 | `llm_call_ledger` row written per call with cost | **PASS** | Real DB: `openai | gpt-4o-mini | extraction | 1648 in | 152 out | $0.0003384 | success` and `cache_hit` row; test `test_ledger_row_written_on_success` asserts `call_kind='extraction'`, `provider='openai'`, `cost > 0` |
| AC #7 | Retry on transient OpenAI errors (3 attempts with exponential backoff) | **PASS** | `test_rate_limit_error_retried_three_times`: `RateLimitError` × 2 then success → 3 provider calls, ledger has 2 `retry` + 1 `success`; `test_all_three_attempts_fail_raises`: 3 calls → raises `LLMProviderError`; `time.sleep` patched to zero in tests |
| AC #8 | 10 hand-crafted synthetic JDs all extract within enum constraints | **PASS** | 10/10 parametrized cases pass: covers Junior/Mid/Senior/Staff/Principal/Lead/Manager/Director seniority; Vancouver/Toronto/Montreal/Calgary/Edmonton/Ottawa/Halifax/Remote-Canada/Remote-NA/Hybrid-Montreal locations; all seniority + location values confirmed in enum |
| AC #9 | Live test (one real posting): all canonical fields populated and valid against enum | **PASS** | Posting #91 (TELUS Digital): `canonical_seniority='Junior'` in enum, `canonical_location='Remote — Canada'` in enum, all 7 fields populated; ledger row confirmed in real DB; live test class `TestLiveExtraction` structurally correct (skipped under SKIP_LIVE=1) |

### Live Extraction Quality (Probabilistic — for user awareness)

- `canonical_title`: "Personalized Internet Assessor" — correct for this role
- `canonical_company`: "TELUS" (model condensed "TELUS Digital" to "TELUS") — division name dropped by the model, not by the suffix stripper; acceptable since TELUS is the parent employer; worth noting for calibration
- `canonical_seniority`: "Junior" — correct (part-time freelance, no experience required)
- `canonical_location`: "Remote — Canada" — correct
- `team_or_department`: "AI Community" (2 words) — reasonable ("TELUS AI Community" is a real program)
- `role_summary`: 4 neutral sentences, no marketing language — good quality for embedding

### Schema Migration

`extraction_cache` table: **present in real DB** (`~/.jd-matcher/jd-matcher.db`) with PRIMARY KEY `(text_hash, model_name)` and 1 row from the live demo. Schema confirmed via `.schema extraction_cache`.

### TASKS.md / Quality Log

- TASK-M2-006 marked `Done (2026-04-27)` — confirmed
- All 9 ACs ticked — confirmed
- Progress summary: Done 6 / To Do 7 / project total 20 — confirmed
- Quality log exists at `docs/poc/quality-logs/TASK-M2-006.md` — confirmed

### Observations

1. **Company-division condensing**: "TELUS Digital" → "TELUS" is a model behavior (not a suffix-stripper artifact). The suffix stripper correctly handles Inc./Ltd./Corp. The division-name behavior is acceptable for M2 dedup but worth tracking in the calibration task.
2. **Posting #91 C19 bypass**: This posting would normally be filtered by C19 ("Internet Assessor" deny pattern). The live extraction demo queries the DB directly, bypassing the C19 filter. This is intentional for the isolated extraction demo; the orchestrator (M2-010) will only invoke `extract_canonical` on postings that passed C19, so #91 will not be re-extracted in normal pipeline flow.
3. **Probabilistic per-field accuracy**: No gold-set evaluation yet (10-15 labeled postings). Per task scope, this is deferred to the calibration task (parallel to M2-004 calibration). The single live result (#91) is noted above for awareness.
4. **AC #4 non-enforcement note**: The `validate_team_word_count` validator logs a WARNING for out-of-range word counts but does not raise `ValidationError`. This is TDD-consistent (the model is prompted to produce 2-5 word values; the validator provides telemetry rather than rejection). The AC is satisfied — the field accepts the canonical format and warns on deviation.

### Overall: PASS

Issues by tier: **None.**
