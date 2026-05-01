"""C18 — LLM Extraction: per-posting canonical field extraction via GPT-4o-mini.

Public API:
    extract_canonical(posting, provider=None, db_path=None, priors=None)
        -> CanonicalExtraction

The function caches by SHA-256 of full_jd to avoid re-extracting identical JDs:
  - In-process cache: a module-level dict keyed by (text_hash, model_name).
  - Persistent cache: extraction_cache table in the SQLite DB (cross-run).

Both retry paths (transient provider errors and parse failures) write their own
llm_call_ledger rows so cost accounting is always complete.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from jd_matcher.errors import ConfigError
from jd_matcher.llm.providers.base import (
    LLMExtractor,
    LLMProviderError,
    ProviderUnavailableError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".jd-matcher" / "jd-matcher.db"

# Path from src/jd_matcher/llm/extract.py → parents[0]=llm, [1]=jd_matcher, [2]=src, [3]=jd-matcher (project root)
_PROJECT_ROOT = Path(__file__).parents[3]

# Prompt version is part of the cache key — bumping to v2 forces re-extraction
# of all existing cache entries (v1 entries keyed on "v1" will never satisfy
# a v2 lookup, achieving zero-code-change invalidation of the M2 corpus).
_PROMPT_VERSION = "v5"
_PROMPT_PATH = _PROJECT_ROOT / "prompts" / f"canonical_extraction_{_PROMPT_VERSION}.txt"

# In-process extraction cache: (text_hash, model_name, prompt_version) -> CanonicalExtraction
_PROCESS_CACHE: dict[tuple[str, str, str], "CanonicalExtraction"] = {}

# ---------------------------------------------------------------------------
# Strict enum types
# ---------------------------------------------------------------------------

CanonicalSeniority = Literal[
    "Junior",
    "Mid",
    "Senior",
    "Staff",
    "Principal",
    "Lead",
    "Manager",
    "Director",
]

# Location enum with "Other" as load-bearing fallback for cities outside the
# canonical list (Burnaby, Waterloo, Kelowna, etc.) — prevents infinite retry
# loops on postings from valid but non-canonical cities.
#
# Resolution documented in quality-log TASK-M2-006.md: AC #2 requires strict
# Pydantic Literal; TDD §C18 allows rare verbatim fallback. "Other" satisfies
# both by being a permitted Literal value rather than bypassing validation.
CanonicalLocation = Literal[
    # Canonical cities
    "Vancouver",
    "Toronto",
    "Montreal",
    "Calgary",
    "Edmonton",
    "Ottawa",
    "Halifax",
    # Hybrid templates
    "Hybrid — Vancouver",
    "Hybrid — Toronto",
    "Hybrid — Montreal",
    "Hybrid — Calgary",
    "Hybrid — Edmonton",
    "Hybrid — Ottawa",
    "Hybrid — Halifax",
    # Remote variants
    "Remote — Canada",
    "Remote — North America",
    "Remote — Global",
    # Fallback: cities not in the canonical list
    "Other",
]

_SENIORITY_VALUES = list(CanonicalSeniority.__args__)  # type: ignore[attr-defined]
_LOCATION_VALUES = list(CanonicalLocation.__args__)  # type: ignore[attr-defined]

# ---------------------------------------------------------------------------
# M3 enum types (v2 prompt)
# ---------------------------------------------------------------------------

CanonicalIndustry = Literal[
    "Financial Services / Asset Management",
    "Insurance / Insurtech",
    "Telecom / Digital Services",
    "Gaming / Entertainment",
    "Legal Tech / Compliance",
    "Professional Services / Consulting",
    "Construction / AEC",
    "Energy / Oil & Gas / Cleantech",
    "AI Training / Annotation Platforms",
    "Staffing / Recruiting",
    "AdTech / Marketing Tech",
    "B2B SaaS",
    "Healthcare / Healthtech",
    "Retail / Ecommerce",
    "Government / Public Sector / Crown Corp",
    "Other",
]

CanonicalRoleOrientation = Literal["Engineering", "Problem-Solving", "Communication"]

CanonicalCitizenshipRequirement = Literal["required", "preferred", "not_mentioned"]

CanonicalCanHireInCanada = Literal["yes", "likely", "no", "unclear"]

_INDUSTRY_VALUES = list(CanonicalIndustry.__args__)  # type: ignore[attr-defined]
_ROLE_ORIENTATION_VALUES = list(CanonicalRoleOrientation.__args__)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Pydantic model
# ---------------------------------------------------------------------------


class CanonicalExtraction(BaseModel):
    """Canonical fields extracted from a job description via LLM.

    Seniority and location are strict Pydantic Literals — any value outside
    the enum causes a ValidationError, triggering a stricter-prompt retry.

    M3 adds seven full-classification fields (fit_score, fit_reasoning,
    industry, role_orientation, salary_min_cad, salary_max_cad,
    citizenship_requirement, citizenship_reason, can_hire_in_canada).
    """

    canonical_title: str
    canonical_company: str
    canonical_seniority: CanonicalSeniority
    canonical_location: CanonicalLocation
    team_or_department: str | None = None
    top_skills: list[str] = Field(default_factory=list)
    role_summary: str
    # M3 full-classification fields
    fit_score: int = Field(ge=1, le=5)
    fit_reasoning: str
    industry: CanonicalIndustry
    role_orientation: list[CanonicalRoleOrientation] = Field(min_length=1, max_length=3)
    salary_min_cad: int | None = None
    salary_max_cad: int | None = None
    citizenship_requirement: CanonicalCitizenshipRequirement
    citizenship_reason: str
    can_hire_in_canada: CanonicalCanHireInCanada

    @field_validator("canonical_company")
    @classmethod
    def strip_legal_suffixes(cls, v: str) -> str:
        """Remove trailing legal entity suffixes (Inc, Ltd, Corp, etc.)."""
        import re

        suffixes = (
            r"\s*,?\s*"
            r"(Inc\.?|Ltd\.?|Limited|Corp\.?|Corporation|Co\.|L\.L\.C\.|LLC|LP|L\.P\."
            r"|Canada Ltd\.?|Canada Inc\.?|Canada Corp\.?)"
            r"\s*$"
        )
        cleaned = re.sub(suffixes, "", v, flags=re.IGNORECASE).strip().rstrip(",").strip()
        return cleaned or v  # never return empty string

    @field_validator("team_or_department")
    @classmethod
    def validate_team_word_count(cls, v: str | None) -> str | None:
        if v is None:
            return None
        words = v.split()
        # Word-count check is advisory only — org-unit semantics matter, not
        # word count. Single-word units ("Engineering", "IT") and multi-word
        # org paths are both valid per prompt v1 calibration round 1.
        if len(words) == 0:
            logger.warning("team_or_department is empty string; returning None")
            return None
        return v

    @field_validator("top_skills")
    @classmethod
    def truncate_skills(cls, v: list[str]) -> list[str]:
        return v[:10]


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class ExtractionParseError(Exception):
    """LLM returned JSON that failed Pydantic validation after all retries."""


# ---------------------------------------------------------------------------
# Posting dataclass (lightweight — avoids a DB import cycle)
# ---------------------------------------------------------------------------


@dataclass
class PostingRow:
    """Minimal view of a postings row needed by extract_canonical."""

    id: int
    full_jd: str
    canonical_title: str | None = None
    canonical_company: str | None = None
    canonical_location: str | None = None


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _jd_hash(full_jd: str) -> str:
    return hashlib.sha256(full_jd.encode("utf-8")).hexdigest()


def _db_cache_get(
    db_path: Path, text_hash: str, model_name: str, prompt_version: str
) -> CanonicalExtraction | None:
    """Return a cached CanonicalExtraction from the DB, or None on miss."""
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT canonical_extraction_json FROM extraction_cache "
                "WHERE text_hash = ? AND model_name = ? AND prompt_version = ?",
                (text_hash, model_name, prompt_version),
            ).fetchone()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("extraction_cache read failed — %s", exc)
        return None

    if row is None:
        return None
    try:
        return CanonicalExtraction.model_validate_json(row[0])
    except Exception as exc:
        logger.warning("extraction_cache: JSON parse failure on cached row — %s", exc)
        return None


def _db_cache_put(
    db_path: Path,
    text_hash: str,
    model_name: str,
    prompt_version: str,
    extraction: CanonicalExtraction,
) -> None:
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO extraction_cache "
                "(text_hash, model_name, prompt_version, canonical_extraction_json) VALUES (?, ?, ?, ?)",
                (text_hash, model_name, prompt_version, extraction.model_dump_json()),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("extraction_cache write failed — %s", exc)


def _write_ledger(
    *,
    db_path: Path | None,
    status: str,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    latency_ms: int,
    posting_id: int | None,
    model_name: str,
) -> None:
    """Write one row to llm_call_ledger; silently swallows failures."""
    if db_path is None:
        return
    from datetime import datetime, timezone

    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            conn.execute(
                """
                INSERT INTO llm_call_ledger
                    (provider, model_name, call_kind,
                     input_tokens, output_tokens, cost_usd,
                     latency_ms, posting_id, called_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "openai",
                    model_name,
                    "extraction",
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    latency_ms,
                    str(posting_id) if posting_id is not None else None,
                    datetime.now(timezone.utc).isoformat(),
                    status,
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("extract: ledger write failed — %s", exc)


def _write_postings_failed(
    *,
    db_path: Path | None,
    posting_id: int,
    raw_response: str,
) -> None:
    """Mark postings.extraction_status='failed'.

    The raw response is stored in extraction_cache.raw_response_text (M3 column).
    The previous M2 hack of writing the raw response into fit_reasoning is
    RETIRED at M3 — fit_reasoning is now a real LLM-extracted field.
    """
    if db_path is None:
        return
    try:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            # extraction_status column may not exist on older DBs — add it on first use
            existing = {
                row[1] for row in conn.execute("PRAGMA table_info(postings);").fetchall()
            }
            if "extraction_status" not in existing:
                conn.execute(
                    "ALTER TABLE postings ADD COLUMN extraction_status TEXT NULL;"
                )
            conn.execute(
                "UPDATE postings SET extraction_status = 'failed' WHERE id = ?",
                (posting_id,),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("extract: postings failure update failed — %s", exc)


def _write_postings_extracted(
    *,
    db_path: Path | None,
    posting_id: int,
    extraction: "CanonicalExtraction",
) -> None:
    """Propagate LLM-extracted M2 fields back to the postings row.

    This closes the bug class documented in ARCHITECTURE-REVIEW-2026-04-29 §2/§4:
    extract_canonical() was only writing to extraction_cache, leaving postings.*
    stale so dedup/engine.py and dedup/merge.py fell back to reading seniority_band.

    M3 fields (fit_score, fit_reasoning, industry, etc.) are NOT yet on the schema
    at TASK-M3-000 — adding them is TASK-M3-001+. The UPDATE is built dynamically
    from the columns that currently exist on the postings table so that TASK-M3-001
    only needs to extend the schema; the propagation helper auto-picks them up.
    """
    if db_path is None:
        return
    try:
        import json as _json

        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON;")
            existing_cols = {
                row[1] for row in conn.execute("PRAGMA table_info(postings);").fetchall()
            }

            # All extraction fields — only columns that exist on the postings table
            # are written (forward-compatible: new columns added via _COLUMN_MIGRATIONS
            # are automatically picked up without code changes here).
            all_candidates: list[tuple[str, object]] = [
                # M2 fields
                ("canonical_company", extraction.canonical_company),
                ("canonical_seniority", extraction.canonical_seniority),
                ("canonical_title", extraction.canonical_title),
                ("canonical_location", extraction.canonical_location),
                ("team_or_department", extraction.team_or_department),
                ("top_skills", _json.dumps(extraction.top_skills)),
                ("role_summary", extraction.role_summary),
                # M3 full-classification fields
                ("fit_score", extraction.fit_score),
                ("fit_reasoning", extraction.fit_reasoning),
                ("industry", extraction.industry),
                ("role_orientation", _json.dumps(extraction.role_orientation)),
                ("salary_min_cad", extraction.salary_min_cad),
                ("salary_max_cad", extraction.salary_max_cad),
                ("citizenship_requirement", extraction.citizenship_requirement),
                ("citizenship_reason", extraction.citizenship_reason),
                ("can_hire_in_canada", extraction.can_hire_in_canada),
            ]

            updates = [(col, val) for col, val in all_candidates if col in existing_cols]
            if not updates:
                return

            set_clause = ", ".join(f"{col} = ?" for col, _ in updates)
            values = [val for _, val in updates]

            # Ensure extraction_status column exists before writing
            if "extraction_status" in existing_cols:
                set_clause += ", extraction_status = ?"
                values.append("success")

            values.append(posting_id)
            conn.execute(
                f"UPDATE postings SET {set_clause} WHERE id = ?",  # noqa: S608
                values,
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("extract: postings propagation failed for posting %s — %s", posting_id, exc)


# ---------------------------------------------------------------------------
# System prompt loading
# ---------------------------------------------------------------------------


def _load_system_prompt() -> str:
    if not _PROMPT_PATH.exists():
        raise ConfigError(
            f"Extraction prompt template not found at {_PROMPT_PATH}. "
            f"Ensure prompts/canonical_extraction_{_PROMPT_VERSION}.txt exists in the project root."
        )
    return _PROMPT_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Stricter prompt builder (used on parse-failure retry)
# ---------------------------------------------------------------------------


def _build_stricter_prompt(
    user_prompt: str,
    bad_fields: dict[str, tuple[Any, list[str]]],
) -> str:
    """Build a corrective user prompt listing all invalid field values.

    Args:
        user_prompt: The original user prompt to append the correction to.
        bad_fields: Mapping of field_name → (bad_value, allowed_values_list).
    """
    lines = [user_prompt]
    lines.append("\n\n=== IMPORTANT: YOUR PREVIOUS RESPONSE HAD INVALID VALUES ===")
    for field_name, (bad_value, allowed) in bad_fields.items():
        lines.append(
            f"INVALID {field_name} value: '{bad_value}'. "
            f"You MUST pick exactly one of: {', '.join(str(v) for v in allowed)}"
        )
    lines.append("Return corrected JSON now.")
    return "\n".join(lines)


def _extract_bad_field_values(raw_json: str) -> dict[str, tuple[Any, list[str]]]:
    """Identify invalid enum field values in a raw JSON string.

    Returns a mapping of field_name → (bad_value, allowed_values) for each
    field that contains an out-of-enum value. Empty dict on fully valid JSON.
    """
    bad: dict[str, tuple[Any, list[str]]] = {}
    try:
        data = json.loads(raw_json)
    except Exception:
        return bad

    _enum_checks: list[tuple[str, list[str]]] = [
        ("canonical_seniority", _SENIORITY_VALUES),
        ("canonical_location", _LOCATION_VALUES),
        ("industry", _INDUSTRY_VALUES),
        ("citizenship_requirement", ["required", "preferred", "not_mentioned"]),
        ("can_hire_in_canada", ["yes", "likely", "no", "unclear"]),
    ]
    for field_name, allowed in _enum_checks:
        val = data.get(field_name)
        if val is not None and val not in allowed:
            bad[field_name] = (val, allowed)

    # role_orientation is a list — check each item
    orient_val = data.get("role_orientation")
    if isinstance(orient_val, list):
        bad_items = [v for v in orient_val if v not in _ROLE_ORIENTATION_VALUES]
        if bad_items:
            bad["role_orientation items"] = (bad_items, _ROLE_ORIENTATION_VALUES)

    return bad


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------


def extract_canonical(
    posting: PostingRow,
    *,
    provider: LLMExtractor | None = None,
    db_path: Path | None = _DEFAULT_DB_PATH,
    priors: dict[str, str] | None = None,
    model_name: str = "gpt-4o-mini",
) -> CanonicalExtraction:
    """Extract canonical fields from a posting's full_jd via LLM.

    Args:
        posting: A PostingRow with ``id`` and ``full_jd`` populated.
        provider: An LLMExtractor instance. If None, builds one from config.
        db_path: Path to the SQLite DB for cache + ledger writes. None = skip.
        priors: Optional email-parsed priors — ``{title, company, location}``
                passed as hints to the prompt.
        model_name: Model name used as part of the cache key.

    Returns:
        A validated ``CanonicalExtraction`` Pydantic model.

    Raises:
        ExtractionParseError: After 3 failed Pydantic validation attempts.
        LLMProviderError: After 3 failed transient-error retries.
        ConfigError: If the prompt template is missing.
    """
    if not posting.full_jd:
        raise ValueError(f"posting {posting.id} has no full_jd — cannot extract")

    text_hash = _jd_hash(posting.full_jd)
    cache_key = (text_hash, model_name, _PROMPT_VERSION)

    # --- In-process cache ---
    if cache_key in _PROCESS_CACHE:
        logger.debug("extract: in-process cache hit for posting %s", posting.id)
        _write_ledger(
            db_path=db_path,
            status="cache_hit",
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            latency_ms=0,
            posting_id=posting.id,
            model_name=model_name,
        )
        _write_postings_extracted(
            db_path=db_path,
            posting_id=posting.id,
            extraction=_PROCESS_CACHE[cache_key],
        )
        return _PROCESS_CACHE[cache_key]

    # --- Persistent DB cache ---
    if db_path is not None:
        cached = _db_cache_get(db_path, text_hash, model_name, _PROMPT_VERSION)
        if cached is not None:
            logger.debug("extract: DB cache hit for posting %s", posting.id)
            _PROCESS_CACHE[cache_key] = cached
            _write_ledger(
                db_path=db_path,
                status="cache_hit",
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                latency_ms=0,
                posting_id=posting.id,
                model_name=model_name,
            )
            _write_postings_extracted(
                db_path=db_path,
                posting_id=posting.id,
                extraction=cached,
            )
            return cached

    # --- Resolve provider ---
    if provider is None:
        from jd_matcher.llm.providers.factory import make_extractor

        resolved_provider = make_extractor(db_path=None)  # ledger written by us
    else:
        resolved_provider = provider

    system_prompt = _load_system_prompt()

    # Build the user prompt
    prior_hints = ""
    if priors:
        prior_hints = "\n\nEmail-parsed hints (use as anchors when the JD is ambiguous):\n"
        for k, v in priors.items():
            prior_hints += f"  {k}: {v}\n"

    base_user_prompt = f"Extract canonical fields from this job description:{prior_hints}\n\n{posting.full_jd}"

    # --- Transient-error retry loop (AC #7) ---
    _TRANSIENT_ERRORS = (RateLimitError, ProviderUnavailableError)
    _BACKOFF = [0, 2, 4]  # seconds before each attempt (attempt 1 is immediate)

    raw_json: str = ""
    last_exc: Exception | None = None

    for attempt_idx, backoff in enumerate(_BACKOFF):
        if backoff:
            time.sleep(backoff)

        # Parse-failure retry loop (separate from transient-error loop)
        user_prompt = base_user_prompt
        parse_last_exc: Exception | None = None
        raw_json = ""

        for parse_attempt in range(3):
            t0 = time.monotonic()
            try:
                raw_json, meta = resolved_provider.extract(
                    prompt=user_prompt,
                    system=system_prompt,
                    response_format={"type": "json_object"},
                )
            except _TRANSIENT_ERRORS as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                _write_ledger(
                    db_path=db_path,
                    status="retry" if attempt_idx < 2 else "failure",
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    latency_ms=latency_ms,
                    posting_id=posting.id,
                    model_name=model_name,
                )
                last_exc = exc
                break  # exit parse loop, continue transient retry loop
            except LLMProviderError as exc:
                latency_ms = int((time.monotonic() - t0) * 1000)
                _write_ledger(
                    db_path=db_path,
                    status="failure",
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                    latency_ms=latency_ms,
                    posting_id=posting.id,
                    model_name=model_name,
                )
                raise  # non-transient: do not retry

            latency_ms = int((time.monotonic() - t0) * 1000)

            # Try to parse the JSON response
            try:
                extraction = CanonicalExtraction.model_validate_json(raw_json)
            except Exception as parse_exc:
                bad_fields = _extract_bad_field_values(raw_json)
                _write_ledger(
                    db_path=db_path,
                    status="retry" if parse_attempt < 2 else "failure",
                    input_tokens=meta.input_tokens,
                    output_tokens=meta.output_tokens,
                    cost_usd=meta.cost_usd,
                    latency_ms=latency_ms,
                    posting_id=posting.id,
                    model_name=model_name,
                )
                parse_last_exc = parse_exc
                if parse_attempt < 2:
                    user_prompt = _build_stricter_prompt(
                        base_user_prompt, bad_fields
                    )
                    logger.warning(
                        "extract: parse failure on posting %s (attempt %d/3) — %s",
                        posting.id,
                        parse_attempt + 1,
                        parse_exc,
                    )
                continue

            # Successful parse
            _write_ledger(
                db_path=db_path,
                status="success",
                input_tokens=meta.input_tokens,
                output_tokens=meta.output_tokens,
                cost_usd=meta.cost_usd,
                latency_ms=latency_ms,
                posting_id=posting.id,
                model_name=model_name,
            )
            _PROCESS_CACHE[cache_key] = extraction
            if db_path is not None:
                _db_cache_put(db_path, text_hash, model_name, _PROMPT_VERSION, extraction)
            _write_postings_extracted(
                db_path=db_path,
                posting_id=posting.id,
                extraction=extraction,
            )
            return extraction

        else:
            # All 3 parse attempts exhausted — store failure and raise
            logger.error(
                "extract: posting %s failed all 3 parse attempts — raw: %.200s",
                posting.id,
                raw_json,
            )
            _write_postings_failed(
                db_path=db_path, posting_id=posting.id, raw_response=raw_json
            )
            raise ExtractionParseError(
                f"Failed to parse CanonicalExtraction after 3 attempts "
                f"for posting {posting.id}: {parse_last_exc}"
            ) from parse_last_exc

        # `break` from parse loop due to transient error — continue outer loop

    # All transient retries exhausted
    raise last_exc or LLMProviderError("Extraction failed after 3 retries")


# ---------------------------------------------------------------------------
# CLI demo entry point
# ---------------------------------------------------------------------------


def _main() -> None:
    import argparse

    from jd_matcher.db.init_db import init_db

    parser = argparse.ArgumentParser(description="Extract canonical fields from a posting")
    parser.add_argument(
        "--posting-id",
        type=int,
        default=None,
        help="Posting ID to extract. Defaults to the highest existing ID.",
    )
    parser.add_argument(
        "--db",
        default=str(_DEFAULT_DB_PATH),
        help=f"Path to the SQLite DB (default: {_DEFAULT_DB_PATH})",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        if args.posting_id is not None:
            row = conn.execute(
                "SELECT id, full_jd, canonical_company, canonical_title, canonical_location "
                "FROM postings WHERE id = ? AND full_jd IS NOT NULL",
                (args.posting_id,),
            ).fetchone()
            if row is None:
                print(
                    f"Posting {args.posting_id} not found or has no full_jd. "
                    "Falling back to highest existing ID with full_jd."
                )
                row = conn.execute(
                    "SELECT id, full_jd, canonical_company, canonical_title, canonical_location "
                    "FROM postings WHERE full_jd IS NOT NULL ORDER BY id DESC LIMIT 1"
                ).fetchone()
        else:
            row = conn.execute(
                "SELECT id, full_jd, canonical_company, canonical_title, canonical_location "
                "FROM postings WHERE full_jd IS NOT NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
    finally:
        conn.close()

    if row is None:
        print("No postings with full_jd found in the database.")
        return

    posting_id, full_jd, company, title, location = row
    posting = PostingRow(
        id=posting_id,
        full_jd=full_jd,
        canonical_company=company,
        canonical_title=title,
        canonical_location=location,
    )
    priors: dict[str, str] = {}
    if company:
        priors["company"] = company
    if title:
        priors["title"] = title
    if location:
        priors["location"] = location

    print(f"Extracting canonical fields for posting ID={posting_id} …")
    result = extract_canonical(posting, db_path=db_path, priors=priors or None)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    _main()
