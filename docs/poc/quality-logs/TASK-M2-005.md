# Quality Log — TASK-M2-005 — LLM Provider Abstraction (C28)

**Date**: 2026-04-27
**Agent**: data-pipeline
**Component**: C28

---

## Pytest Summary

```
630 passed, 1 skipped, 0 warnings-causing-failures in 11.40s
```

New tests added: 45 (all in `tests/llm/providers/`)

All pre-existing tests (585) continue to pass — no regressions.

---

## Demo Artifact

```
$ .venv/bin/python -c "from jd_matcher.llm import LLMExtractor; e = LLMExtractor.from_config(); print(type(e).__name__)"
OpenAIExtractor
```

---

## Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | `LLMExtractor` + `EmbeddingProvider` Protocols defined with `extract()` / `embed()` | PASS | `test_base.py` — isinstance checks pass |
| 2 | `OpenAIExtractor` using GPT-4o-mini (configurable) | PASS | default `model="gpt-4o-mini"`, overridable; `test_openai_extractor.py` |
| 3 | `OpenAIEmbedding` using `text-embedding-3-small` | PASS | default `model="text-embedding-3-small"`; `test_openai_embedding.py` |
| 4 | Ollama stubs raise `NotImplementedError` with M3 message | PASS | `test_ollama_stubs.py` — all 6 tests pass |
| 5 | Factory pattern: `from_config()` returns correct impl | PASS | `test_factory.py` — 8 tests cover classmethod + free function |
| 6 | Pricing table with `model` + `input_cost_per_1k` + `output_cost_per_1k` + `as_of_date` | PASS | `pricing.py` PRICING_TABLE; `test_pricing.py` — 8 tests |
| 7 | `llm_call_ledger` row written per call | PASS | `test_ledger_writes.py` — real tmp SQLite; 5 tests including success+failure paths for both extract and embed |
| 8 | Tests mock at openai client boundary (no live calls) | PASS | all tests use `@patch("...openai.OpenAI")`; zero live calls |

---

## Ledger Write Evidence (from test_ledger_writes.py)

After a mocked `extractor.extract()` call against a real tmp SQLite:

```python
# Row in llm_call_ledger after successful extract:
{
  "provider": "openai",
  "model_name": "gpt-4o-mini",
  "call_kind": "extraction",
  "input_tokens": 200,
  "output_tokens": 30,
  "cost_usd": 0.000048,    # (200/1000)*0.00015 + (30/1000)*0.00060
  "latency_ms": <>=0>,
  "posting_id": null,
  "status": "success"
}

# Row after failed extract (RateLimitError):
{
  "status": "failure",
  "cost_usd": 0.0,
  "input_tokens": 0,
  "output_tokens": 0
}

# Embedding row:
{
  "call_kind": "embedding",
  "output_tokens": null,   # embeddings have no output tokens
  "status": "success"
}
```

---

## Implementation Decisions Noted

1. **Config approach**: `config/llm.yaml` (per-domain YAML matching title_filters pattern). File is optional — missing falls back to baked-in defaults.
2. **Factory entry point**: `LLMExtractor.from_config()` classmethod attached at module-level in `llm/__init__.py` via lambda delegation to `make_extractor()`. Free functions `make_extractor()`/`make_embedder()` in `factory.py` satisfy AC #5 regardless of entry point used.
3. **Ledger writes**: auto-written inside provider (`db_path=None` disables silently). Failure path writes a `status='failure'` row before re-raising translated exception.
4. **Error translation**: `openai.RateLimitError` → `RateLimitError`; `openai.APIConnectionError` → `ProviderUnavailableError`; all other `openai.OpenAIError` → `LLMProviderError`.
5. **Ollama stubs**: raise `NotImplementedError` on `__init__` (not on method calls), so accidental instantiation fails immediately rather than on first use.
6. **Protocol classmethod**: `LLMExtractor` and `EmbeddingProvider` are `@runtime_checkable` Protocols with `from_config()` declared. The actual routing logic lives in `factory.py`; the Protocol's `from_config()` is patched at import time in `__init__.py`. C18/C20 need only `from jd_matcher.llm import LLMExtractor`.
7. **Pricing table**: `as_of_date="2026-04-27"` with source URL comment. `compute_cost()` returns 0.0 for unknown models (with a warning log).
8. **`_DEFAULT_DB_PATH`**: consistent with `init_db.py` (`~/.jd-matcher/jd-matcher.db`).

---

## No Issues / Flags

- No new dependencies required (`openai` and `pydantic` already pinned from M2-002).
- No architectural concerns — abstraction is airtight; C18/C20 import only from `jd_matcher.llm`.
- OpenAI SDK API surface used: `client.chat.completions.create()` (extraction), `client.embeddings.create()` (embedding) — both stable since SDK v1.0.

---

## Independent Validation (test-validator, 2026-04-27)

**Validator**: test-validator agent (claude-sonnet-4-6)
**Commit validated**: 97c377d

### Test Suite

630 passed, 1 skipped (SKIP_LIVE-gated Indeed pagead live HTTP), 0 failed — matches implementer claim.
New tests in `tests/llm/providers/`: 45 — confirmed by directory listing and isolated run.

### Per-AC Verdicts

| AC | Criterion | Verdict | Evidence |
|----|-----------|---------|----------|
| #1 | Protocols defined with `extract()` / `embed()` | PASS | `base.py` — `@runtime_checkable class LLMExtractor(Protocol)` and `EmbeddingProvider(Protocol)`; `extract()` and `embed()` declared with correct signatures; `ExtractionMetadata`, `EmbeddingMetadata` dataclasses present; `RateLimitError`, `ProviderUnavailableError`, `LLMProviderError` exceptions present; `isinstance` checks pass at runtime |
| #2 | `OpenAIExtractor` using GPT-4o-mini (configurable) | PASS | `openai_extractor.py` line 44: `model: str = "gpt-4o-mini"`; constructor-configurable; uses `openai` SDK; uses `get_openai_key()` from M2-002 via lazy `_get_client()` |
| #3 | `OpenAIEmbedding` using `text-embedding-3-small` | PASS | `openai_embedding.py` line 39: `model: str = "text-embedding-3-small"`; constructor-configurable; uses `openai` SDK; uses `get_openai_key()` |
| #4 | Ollama stubs raise `NotImplementedError` with M3 message | PASS | Both `ollama_extractor.py` and `ollama_embedding.py` raise on `__init__`; message explicitly mentions "M3 cloud-vs-local benchmark sub-task"; exercised live: confirmed |
| #5 | Factory pattern routes correctly | PASS | `factory.py` — `make_extractor('openai')` returns `OpenAIExtractor`; `make_extractor('ollama')` raises `NotImplementedError`; unknown provider `'anthropic'` raises `ValueError` with available providers listed; `LLMExtractor.from_config()` and `EmbeddingProvider.from_config()` both return correct types |
| #6 | Pricing table with required fields + `as_of_date` | PASS | `pricing.py` PRICING_TABLE has `gpt-4o-mini` (`input_cost_per_1k=0.00015`, `output_cost_per_1k=0.00060`, `as_of_date="2026-04-27"`) and `text-embedding-3-small` (`input_cost_per_1k=0.00002`, `output_cost_per_1k=None`, `as_of_date="2026-04-27"`); `compute_cost('gpt-4o-mini', 1000, 200)` = $0.000270 (correct) |
| #7 | `llm_call_ledger` row per call | PASS | Exercised with real tmp SQLite + mocked OpenAI client: 2 rows written (extraction + embedding), correct fields including `provider`, `model_name`, `call_kind`, `input_tokens`, `output_tokens` (NULL for embedding), `cost_usd > 0`, `latency_ms >= 0`, `status='success'`; failure path: `RateLimitError` → ledger row with `status='failure'`, `cost_usd=0.0` written before re-raise |
| #8 | Tests mock at openai boundary (no live calls) | PASS | All references to `openai.OpenAI`, `client.chat`, `client.embeddings` in test files are inside `@patch("jd_matcher.llm.providers.openai_extractor.openai.OpenAI")` or `@patch("jd_matcher.llm.providers.openai_embedding.openai.OpenAI")` decorators — confirmed by grep |

### Demo Artifacts

- `LLMExtractor.from_config()` returns `OpenAIExtractor` — confirmed
- `EmbeddingProvider.from_config()` returns `OpenAIEmbedding` — confirmed

### Ledger Write Evidence (independent exercise)

Extractor row: `('openai', 'gpt-4o-mini', 'extraction', 100, 25, 2.999...e-05, 0, 'success')`
Embedder row: `('openai', 'text-embedding-3-small', 'embedding', 50, None, 1.000...e-06, 0, 'success')`
Failure row: `[('extraction', 'failure', 0.0)]`

### Failure-Path Error Translation

`openai.RateLimitError` correctly translated to `jd_matcher.llm.providers.base.RateLimitError` — confirmed.

### Backward Compat

`get_openai_key()` still importable from `jd_matcher.llm` and returns correct value — confirmed.

### Classmethod-on-Protocol Pattern

Importing `providers.base.LLMExtractor` before `jd_matcher.llm` (which patches it) does not break `from_config()` — the Protocol object is the same in both modules (`BaseExtractor is LLMExtractor` = True), so the patch applied at `llm.__init__` import time persists. No circular import issues detected.

### TASKS.md / Quality Log

- TASK-M2-005 marked `Done (2026-04-27)` with all 8 ACs `[x]` — confirmed
- Progress Summary: Done 5, To Do 8, project total Done 19 — confirmed
- Quality log `docs/poc/quality-logs/TASK-M2-005.md` existed with per-AC verdicts and demo evidence — confirmed

### Overall: PASS

No issues found. No Minor, Major, or Directional findings.

**Observations (not failures)**:
- The classmethod-on-Protocol lambda-delegation pattern (`llm/__init__.py` lines 72-81) is unusual. It works correctly and survives the "import base before llm" ordering because the Protocol class object is shared by reference. The risk is if someone calls `LLMExtractor.from_config()` before `jd_matcher.llm` has been imported (i.e., imports only from `jd_matcher.llm.providers.base`). In that case `from_config` would invoke the Protocol's stub `...` body instead of routing to the factory. This scenario is unlikely given the module structure, but worth noting for the implementer of C18/C20: always import from `jd_matcher.llm`, not from `jd_matcher.llm.providers.base`.
- `latency_ms` records 0 ms for mocked calls (perf_counter measures the mock overhead only) — expected and correct behavior in tests.
- Pricing figures are as of 2026-04-27; OpenAI pricing changes should trigger a `pricing.py` update before the M3 cost benchmark runs.
