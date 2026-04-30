"""Unit tests for C32 — LLM Dedup Gatekeeper (LLMDedupClassifier).

Coverage:
  - Happy path: LLM returns valid JSON → GatekeeperVerdict returned
  - Parse error on first attempt, success on retry
  - Parse error on all attempts → None returned (fail-CLOSED)
  - API error on all attempts → None returned (fail-CLOSED)
  - Ledger write triggered on success and failure
  - GatekeeperVerdict Pydantic model validation
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jd_matcher.dedup.classifier import GatekeeperVerdict, LLMDedupClassifier
from jd_matcher.llm.providers.base import ExtractionMetadata, LLMProviderError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_extractor_mock(
    responses: list[str | Exception],
    tokens: int = 1000,
    cost_usd: float = 0.00015,
    latency_ms: int = 500,
) -> MagicMock:
    """Build a mock LLMExtractor that returns the given sequence of responses."""
    meta = ExtractionMetadata(
        input_tokens=tokens,
        output_tokens=50,
        latency_ms=latency_ms,
        cost_usd=cost_usd,
    )
    mock = MagicMock()
    call_results = []
    for resp in responses:
        if isinstance(resp, Exception):
            call_results.append(resp)
        else:
            call_results.append((resp, meta))

    def _extract(prompt, system, response_format):
        item = call_results.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    mock.extract.side_effect = _extract
    return mock


_PROMPT_TEMPLATE = (
    "Company A: {a_company} Title A: {a_title} JD A: {a_full_jd}\n"
    "Company B: {b_company} Title B: {b_title} JD B: {b_full_jd}\n"
    "Return JSON: is_same_role + reasoning"
)

_POSTING_A = {
    "id": 1,
    "canonical_title": "Senior Data Scientist",
    "canonical_company": "Shopify",
    "full_jd": "We are hiring a Senior Data Scientist for our Merchant Analytics team.",
}
_POSTING_B = {
    "id": 2,
    "canonical_title": "Senior Data Scientist",
    "canonical_company": "Shopify",
    "full_jd": "Shopify Merchant Analytics is looking for a Senior Data Scientist.",
}
_POSTING_DIFFERENT = {
    "id": 3,
    "canonical_title": "Senior Data Scientist",
    "canonical_company": "Shopify",
    "full_jd": "The Risk Analytics team at Shopify is hiring a Senior Data Scientist for fraud modelling.",
}

_VERDICT_SAME = '{"is_same_role": true, "reasoning": "Both postings describe the same role."}'
_VERDICT_DIFF = '{"is_same_role": false, "reasoning": "Different teams — one is Risk, one is Merchant."}'


# ---------------------------------------------------------------------------
# GatekeeperVerdict model
# ---------------------------------------------------------------------------


class TestGatekeeperVerdict:
    def test_valid_same_role(self):
        v = GatekeeperVerdict.model_validate_json(_VERDICT_SAME)
        assert v.is_same_role is True
        assert "same role" in v.reasoning.lower()

    def test_valid_different_role(self):
        v = GatekeeperVerdict.model_validate_json(_VERDICT_DIFF)
        assert v.is_same_role is False

    def test_missing_field_raises(self):
        with pytest.raises(Exception):
            GatekeeperVerdict.model_validate_json('{"is_same_role": true}')

    def test_extra_fields_ignored(self):
        v = GatekeeperVerdict.model_validate_json(
            '{"is_same_role": false, "reasoning": "Different.", "model_name": "gpt-4o"}'
        )
        assert v.is_same_role is False


# ---------------------------------------------------------------------------
# LLMDedupClassifier — happy path
# ---------------------------------------------------------------------------


class TestLLMDedupClassifierHappyPath:
    def test_same_role_verdict_returned(self):
        mock = _make_extractor_mock([_VERDICT_SAME])
        classifier = LLMDedupClassifier(
            llm_client=mock,
            prompt_template=_PROMPT_TEMPLATE,
            db_path=None,
        )
        verdict = classifier.classify(_POSTING_A, _POSTING_B, fuse_score=0.88)
        assert verdict is not None
        assert verdict.is_same_role is True
        assert mock.extract.call_count == 1

    def test_different_role_verdict_returned(self):
        mock = _make_extractor_mock([_VERDICT_DIFF])
        classifier = LLMDedupClassifier(
            llm_client=mock,
            prompt_template=_PROMPT_TEMPLATE,
            db_path=None,
        )
        verdict = classifier.classify(_POSTING_A, _POSTING_DIFFERENT, fuse_score=0.80)
        assert verdict is not None
        assert verdict.is_same_role is False

    def test_fuse_score_recorded_in_logs(self, caplog):
        mock = _make_extractor_mock([_VERDICT_SAME])
        classifier = LLMDedupClassifier(
            llm_client=mock,
            prompt_template=_PROMPT_TEMPLATE,
            db_path=None,
        )
        import logging
        with caplog.at_level(logging.DEBUG, logger="jd_matcher.dedup.classifier"):
            classifier.classify(_POSTING_A, _POSTING_B, fuse_score=0.877)
        # fuse score is in the debug log
        assert "0.877" in caplog.text


# ---------------------------------------------------------------------------
# Retry behavior: parse error on first attempt, success on retry
# ---------------------------------------------------------------------------


class TestLLMDedupClassifierRetry:
    def test_parse_error_first_attempt_retries_success(self):
        """First call returns bad JSON; second call (retry) returns valid JSON."""
        mock = _make_extractor_mock([
            '{"not_a_verdict": true}',  # parse error — missing 'reasoning'
            _VERDICT_SAME,             # retry succeeds
        ])
        classifier = LLMDedupClassifier(
            llm_client=mock,
            prompt_template=_PROMPT_TEMPLATE,
            db_path=None,
        )
        verdict = classifier.classify(_POSTING_A, _POSTING_B, retry_count=1)
        assert verdict is not None
        assert verdict.is_same_role is True
        assert mock.extract.call_count == 2

    def test_api_error_first_attempt_retries_success(self):
        """First call raises LLMProviderError; second call succeeds."""
        mock = _make_extractor_mock([
            LLMProviderError("Connection timed out"),
            _VERDICT_SAME,
        ])
        classifier = LLMDedupClassifier(
            llm_client=mock,
            prompt_template=_PROMPT_TEMPLATE,
            db_path=None,
        )
        verdict = classifier.classify(_POSTING_A, _POSTING_B, retry_count=1)
        assert verdict is not None
        assert verdict.is_same_role is True
        assert mock.extract.call_count == 2


# ---------------------------------------------------------------------------
# Fail-CLOSED: both attempts fail → None
# ---------------------------------------------------------------------------


class TestLLMDedupClassifierFailClosed:
    def test_double_parse_error_returns_none(self):
        """Both calls return invalid JSON → classifier returns None (fail-CLOSED)."""
        mock = _make_extractor_mock([
            '{"invalid": "no reasoning field here"}',
            '{"also_bad": "still no reasoning"}',
        ])
        classifier = LLMDedupClassifier(
            llm_client=mock,
            prompt_template=_PROMPT_TEMPLATE,
            db_path=None,
        )
        result = classifier.classify(_POSTING_A, _POSTING_B, retry_count=1)
        assert result is None
        assert mock.extract.call_count == 2

    def test_double_api_error_returns_none(self):
        """Both calls raise LLMProviderError → classifier returns None (fail-CLOSED)."""
        mock = _make_extractor_mock([
            LLMProviderError("Rate limit"),
            LLMProviderError("Rate limit again"),
        ])
        classifier = LLMDedupClassifier(
            llm_client=mock,
            prompt_template=_PROMPT_TEMPLATE,
            db_path=None,
        )
        result = classifier.classify(_POSTING_A, _POSTING_B, retry_count=1)
        assert result is None
        assert mock.extract.call_count == 2

    def test_mixed_failures_returns_none(self):
        """API error then parse error → None."""
        mock = _make_extractor_mock([
            LLMProviderError("Timeout"),
            '{"malformed json...}',
        ])
        classifier = LLMDedupClassifier(
            llm_client=mock,
            prompt_template=_PROMPT_TEMPLATE,
            db_path=None,
        )
        result = classifier.classify(_POSTING_A, _POSTING_B, retry_count=1)
        assert result is None

    def test_zero_retry_count_means_one_attempt(self):
        """retry_count=0 → only 1 total attempt, not 2."""
        mock = _make_extractor_mock([
            LLMProviderError("Single fail"),
        ])
        classifier = LLMDedupClassifier(
            llm_client=mock,
            prompt_template=_PROMPT_TEMPLATE,
            db_path=None,
        )
        result = classifier.classify(_POSTING_A, _POSTING_B, retry_count=0)
        assert result is None
        assert mock.extract.call_count == 1


# ---------------------------------------------------------------------------
# Ledger write (with a real temp DB)
# ---------------------------------------------------------------------------


def _make_test_db_with_ledger() -> tuple[sqlite3.Connection, Path]:
    """Create a temporary SQLite DB with the minimal ledger schema."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    db_path = Path(tmp.name)
    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            created_at TIMESTAMP NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        );
        INSERT OR IGNORE INTO users (id) VALUES ('default');

        CREATE TABLE IF NOT EXISTS llm_call_ledger (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      TEXT NOT NULL DEFAULT 'default',
            provider     TEXT NOT NULL,
            model_name   TEXT NOT NULL,
            call_kind    TEXT NOT NULL,
            input_tokens INTEGER NULL,
            output_tokens INTEGER NULL,
            cost_usd     REAL NOT NULL DEFAULT 0.0,
            latency_ms   INTEGER NOT NULL,
            posting_id   TEXT NULL,
            called_at    TIMESTAMP NOT NULL,
            status       TEXT NOT NULL,
            notes        TEXT NULL
        );
    """)
    conn.commit()
    conn.close()
    return db_path


class TestLedgerWrites:
    def test_success_writes_ledger_row(self):
        db_path = _make_test_db_with_ledger()
        try:
            mock = _make_extractor_mock([_VERDICT_SAME])
            classifier = LLMDedupClassifier(
                llm_client=mock,
                prompt_template=_PROMPT_TEMPLATE,
                db_path=db_path,
            )
            classifier.classify(_POSTING_A, _POSTING_B, fuse_score=0.85)

            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT call_kind, status, notes FROM llm_call_ledger WHERE call_kind='dedup_gatekeeper'"
            ).fetchall()
            conn.close()

            assert len(rows) == 1
            row = rows[0]
            assert row[0] == "dedup_gatekeeper"
            assert row[1] == "success"
            notes = json.loads(row[2])
            assert "fuse_score" in notes
            assert notes["is_same_role"] is True

        finally:
            db_path.unlink(missing_ok=True)

    def test_failure_writes_ledger_row_with_failure_status(self):
        db_path = _make_test_db_with_ledger()
        try:
            mock = _make_extractor_mock([
                LLMProviderError("fail"),
                LLMProviderError("fail again"),
            ])
            classifier = LLMDedupClassifier(
                llm_client=mock,
                prompt_template=_PROMPT_TEMPLATE,
                db_path=db_path,
            )
            result = classifier.classify(_POSTING_A, _POSTING_B, retry_count=1)
            assert result is None

            conn = sqlite3.connect(db_path)
            rows = conn.execute(
                "SELECT call_kind, status, notes FROM llm_call_ledger WHERE call_kind='dedup_gatekeeper'"
            ).fetchall()
            conn.close()

            assert len(rows) == 1
            assert rows[0][1] in ("api_error", "pending_after_retry")
            notes = json.loads(rows[0][2])
            assert notes["is_same_role"] is None

        finally:
            db_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Prompt v2 structure — hiring-agent guard
# ---------------------------------------------------------------------------


class TestPromptV2Structure:
    """Verify the prompt file contains the v2 framing required for hiring-agent guard.

    These tests read the actual prompt file on disk so they catch accidental
    reversion without re-running live LLM calls.
    """

    def _load_prompt_text(self) -> str:
        from jd_matcher.dedup.classifier import _load_prompt
        return _load_prompt()

    def test_prompt_default_different_framing_present(self):
        """Prompt must assert 'different' as the default assumption."""
        text = self._load_prompt_text().lower()
        assert "default" in text and "different" in text, (
            "v2 prompt must state that postings are assumed DIFFERENT by default"
        )

    def test_prompt_staffing_firm_guard_keywords_present(self):
        """Prompt must include staffing-firm indicator keywords."""
        text = self._load_prompt_text().lower()
        staffing_indicators = ["recruiting", "staffing", "search"]
        assert any(kw in text for kw in staffing_indicators), (
            "v2 prompt must include staffing-firm guard keywords (Recruiting/Staffing/Search)"
        )

    def test_hiring_agent_pair_via_real_prompt_template(self):
        """Gatekeeper with v2 prompt returns a verdict for a hiring-agent pair.

        Uses a mock LLM returning 'different' — verifies the prompt template
        formats correctly with staffing-firm company names and the classifier
        surfaces the verdict without error.
        """
        from jd_matcher.dedup.classifier import LLMDedupClassifier, _load_prompt
        from jd_matcher.llm.providers.base import ExtractionMetadata

        verdict_json = '{"is_same_role": false, "reasoning": "Staffing firm — different client mandates, no shared job ID."}'
        meta = ExtractionMetadata(input_tokens=800, output_tokens=40, latency_ms=300, cost_usd=0.00012)
        mock = MagicMock()
        mock.extract.return_value = (verdict_json, meta)

        prompt = _load_prompt()
        classifier = LLMDedupClassifier(
            llm_client=mock,
            prompt_template=prompt,
            db_path=None,
        )
        posting_agency_a = {
            "id": 10,
            "canonical_title": "Data Scientist",
            "canonical_company": "Alquemy Search & Consulting",
            "full_jd": "Our financial services client needs a Data Scientist. Python, ML, SQL.",
        }
        posting_agency_b = {
            "id": 11,
            "canonical_title": "Data Scientist",
            "canonical_company": "Alquemy Search & Consulting",
            "full_jd": "Insurance client in Vancouver seeking a Data Scientist. Python, ML, SQL.",
        }
        result = classifier.classify(posting_agency_a, posting_agency_b, fuse_score=0.90)
        assert result is not None
        assert result.is_same_role is False
        assert "staffing" in result.reasoning.lower() or "client" in result.reasoning.lower()
