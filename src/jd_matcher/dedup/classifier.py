"""C32 — LLM Dedup Gatekeeper.

Public API:
    LLMDedupClassifier.classify(posting_a, posting_b) -> GatekeeperVerdict | None

Dispatched by C21.decide() when a candidate pair scores in the borderline band
[gatekeeper_threshold, exact-match-short-circuit).  Returns a GatekeeperVerdict
(is_same_role + reasoning) or None if both retry attempts hard-fail.

Fail-CLOSED contract (Decision 2, TASK-M2-012):
    - Retry once on any failure (API error, JSON parse error, schema error).
    - After 2 total failures: return None.  C21 sets action='pending_gatekeeper'.
    - A pending_gatekeeper posting is NOT merged and NOT written to
      posting_canonical_links.  Next pipeline run retries.

Telemetry: every call (success or fail) writes one llm_call_ledger row with
call_kind='dedup_gatekeeper'.  The notes column carries a JSON payload with
both posting IDs, fuse_score, verdict, and retry count.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from jd_matcher.llm.providers.base import LLMExtractor, LLMProviderError

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"
# prompts/dedup_classifier_v1.txt: 4 levels up from src/jd_matcher/dedup/classifier.py
_PROMPT_PATH = Path(__file__).parents[3] / "prompts" / "dedup_classifier_v1.txt"


# ---------------------------------------------------------------------------
# Output model
# ---------------------------------------------------------------------------


class GatekeeperVerdict(BaseModel):
    """LLM verdict returned by the dedup gatekeeper."""

    is_same_role: bool
    reasoning: str  # 1-2 sentences explaining the decision


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class GatekeeperParseError(Exception):
    """LLM response could not be parsed / validated as GatekeeperVerdict."""


# ---------------------------------------------------------------------------
# Ledger writer
# ---------------------------------------------------------------------------


def _write_ledger(
    *,
    db_path: Path | None,
    model_name: str,
    status: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    notes: dict[str, Any],
) -> None:
    """Write one row to llm_call_ledger; silently swallows failures."""
    if db_path is None:
        return
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute(
                """
                INSERT INTO llm_call_ledger
                    (provider, model_name, call_kind,
                     input_tokens, output_tokens, cost_usd,
                     latency_ms, posting_id, called_at, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "openai",
                    model_name,
                    "dedup_gatekeeper",
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    latency_ms,
                    None,  # posting_id — pair-level call, not posting-level
                    datetime.now(timezone.utc).isoformat(),
                    status,
                    json.dumps(notes),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("gatekeeper: ledger write failed — %s", exc)


# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------


def _load_prompt() -> str:
    if not _PROMPT_PATH.exists():
        raise FileNotFoundError(
            f"Dedup classifier prompt not found at {_PROMPT_PATH}. "
            "Ensure prompts/dedup_classifier_v1.txt exists in the project root."
        )
    return _PROMPT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class LLMDedupClassifier:
    """C32 — calls the LLM gatekeeper for borderline dedup pairs.

    Args:
        llm_client: An LLMExtractor instance (C28 interface — no SDK imports here).
        prompt_template: The raw prompt string with {a_title}, {a_company},
            {a_full_jd}, {b_title}, {b_company}, {b_full_jd} placeholders.
        db_path: SQLite DB path for llm_call_ledger writes.  None = no telemetry.
        model_name: Model name recorded in the ledger (default: gpt-4o-mini).
    """

    def __init__(
        self,
        llm_client: LLMExtractor,
        prompt_template: str,
        db_path: Path | None = _DEFAULT_DB_PATH,
        model_name: str = "gpt-4o-mini",
    ) -> None:
        self._client = llm_client
        self._prompt_template = prompt_template
        self._db_path = db_path
        self._model_name = model_name
        # Updated after every classify() call — lets callers (e.g. calibrate.py) read cost.
        self.last_call_cost_usd: float = 0.0

    def classify(
        self,
        posting_a: dict[str, Any],
        posting_b: dict[str, Any],
        *,
        fuse_score: float = 0.0,
        retry_count: int = 1,
    ) -> GatekeeperVerdict | None:
        """Classify a pair of postings as same-role or different.

        Args:
            posting_a: Dict with keys: full_jd, canonical_title, canonical_company.
            posting_b: Dict with keys: full_jd, canonical_title, canonical_company.
            fuse_score: The FUSE similarity score that triggered this call (recorded
                in the ledger for traceability).
            retry_count: Number of retry attempts on failure (default: 1 → 2 total
                attempts). Must be >= 0.

        Returns:
            GatekeeperVerdict on success, None if all attempts fail.
        """
        total_attempts = 1 + retry_count
        last_status = "api_error"
        input_tokens = 0
        output_tokens = 0
        cost_usd = 0.0
        latency_ms = 0
        self.last_call_cost_usd = 0.0

        # Indent the full_jd for readable prompt presentation
        a_jd = (posting_a.get("full_jd") or "").strip()
        b_jd = (posting_b.get("full_jd") or "").strip()
        a_jd_indented = "\n".join("  " + line for line in a_jd.splitlines()) if a_jd else "  (no JD text available)"
        b_jd_indented = "\n".join("  " + line for line in b_jd.splitlines()) if b_jd else "  (no JD text available)"

        user_prompt = self._prompt_template.format(
            a_title=posting_a.get("canonical_title") or "",
            a_company=posting_a.get("canonical_company") or "",
            a_full_jd=a_jd_indented,
            b_title=posting_b.get("canonical_title") or "",
            b_company=posting_b.get("canonical_company") or "",
            b_full_jd=b_jd_indented,
        )
        # The prompt file is self-contained; use an empty system prompt so the
        # full instruction set is in the user turn (consistent with how the
        # extraction extractor handles its own prompt layout).
        system_prompt = ""

        for attempt in range(total_attempts):
            t0 = time.monotonic()
            try:
                raw_json, meta = self._client.extract(
                    prompt=user_prompt,
                    system=system_prompt,
                    response_format={"type": "json_object"},
                )
                latency_ms = int((time.monotonic() - t0) * 1000)
                input_tokens = meta.input_tokens
                output_tokens = meta.output_tokens
                cost_usd = meta.cost_usd
            except LLMProviderError as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                last_status = "api_error"
                logger.warning(
                    "gatekeeper: API error on attempt %d/%d — %s",
                    attempt + 1,
                    total_attempts,
                    exc,
                )
                continue

            # Try to parse the verdict
            try:
                verdict = GatekeeperVerdict.model_validate_json(raw_json)
                last_status = "success"
                self.last_call_cost_usd = cost_usd
                _write_ledger(
                    db_path=self._db_path,
                    model_name=self._model_name,
                    status="success",
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cost_usd=cost_usd,
                    latency_ms=latency_ms,
                    notes={
                        "posting_a_id": posting_a.get("id"),
                        "posting_b_id": posting_b.get("id"),
                        "fuse_score": fuse_score,
                        "is_same_role": verdict.is_same_role,
                        "reasoning": verdict.reasoning,
                        "retry_count": attempt,
                    },
                )
                logger.debug(
                    "gatekeeper: verdict=%s reasoning=%s (fuse=%.3f attempt=%d)",
                    verdict.is_same_role,
                    verdict.reasoning,
                    fuse_score,
                    attempt + 1,
                )
                return verdict
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_status = "parse_error"
                logger.warning(
                    "gatekeeper: parse error on attempt %d/%d — %s — raw: %.200s",
                    attempt + 1,
                    total_attempts,
                    exc,
                    raw_json,
                )
                continue

        # All attempts failed
        _write_ledger(
            db_path=self._db_path,
            model_name=self._model_name,
            status="pending_after_retry" if last_status == "api_error" else last_status,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            notes={
                "posting_a_id": posting_a.get("id"),
                "posting_b_id": posting_b.get("id"),
                "fuse_score": fuse_score,
                "is_same_role": None,
                "reasoning": None,
                "retry_count": total_attempts - 1,
                "failure_reason": last_status,
            },
        )
        logger.error(
            "gatekeeper: all %d attempts failed for pair (%s, %s) — fail-CLOSED",
            total_attempts,
            posting_a.get("id"),
            posting_b.get("id"),
        )
        return None


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


def make_classifier(db_path: Path | None = _DEFAULT_DB_PATH) -> LLMDedupClassifier:
    """Build a LLMDedupClassifier using the default C28 LLM provider."""
    from jd_matcher.llm.providers.factory import make_extractor

    client = make_extractor(db_path=None)  # ledger written by classifier directly
    prompt = _load_prompt()
    return LLMDedupClassifier(llm_client=client, prompt_template=prompt, db_path=db_path)
