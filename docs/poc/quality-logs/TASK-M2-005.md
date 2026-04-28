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
