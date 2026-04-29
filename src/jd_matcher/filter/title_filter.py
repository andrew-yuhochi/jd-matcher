"""
Title-Based Interest Filter (C19) — pre-LLM cheap heuristic filter.

Evaluation logic:
  1. Decode HTML entities in the title (so &amp; → &, &#38; → &, etc.).
  2. Check pre_deny[] patterns FIRST against title (case-insensitive). If any
     match → DROP unconditionally (no allow override can rescue these — used for
     entry-level and similar absolute disqualifiers that override even ML/Data
     context).
  3. Check deny_company[] patterns against company (case-insensitive). If any
     match → DROP unconditionally. Skipped entirely when company is None/empty.
  4. Check allow[] patterns (case-insensitive). If any match → PASS.
  5. Check deny[] patterns (case-insensitive). If any match → DROP.
  6. No match in either list → PASS.

Config is loaded once per process from config/title_filters.yaml and
cached via a module-level sentinel. Callers may pass a custom TitleFilters
object to override (used in tests).
"""

from __future__ import annotations

import argparse
import html
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Resolved at import time: src/jd_matcher/filter/ → project root → config/
_DEFAULT_CONFIG_PATH = Path(__file__).parents[3] / "config" / "title_filters.yaml"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class FilterPattern(BaseModel):
    pattern: str
    kind: Literal["regex", "substring"]
    note: str = ""


class TitleFilters(BaseModel):
    pre_deny: list[FilterPattern] = []      # title-based, checked first — no rescue possible
    deny_company: list[FilterPattern] = []  # company-based, checked after pre_deny — no rescue possible
    allow: list[FilterPattern] = []         # title-based escape hatch from deny[]
    deny: list[FilterPattern] = []          # title-based default-drop


class FilterDecision(BaseModel):
    action: Literal["pass", "drop"]
    matched_pattern: str | None = None
    reason: str | None = None


# ---------------------------------------------------------------------------
# Config loader (cached per config path)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=4)
def load_filters(config_path: Path | None = None) -> TitleFilters:
    """Load and parse title_filters.yaml, returning a TitleFilters model.

    Cached per config_path so the file is read at most once per process.
    Pass a different path in tests to isolate from the project config.
    """
    resolved = config_path or _DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    return TitleFilters(
        pre_deny=[FilterPattern(**p) for p in (raw.get("pre_deny") or [])],
        deny_company=[FilterPattern(**p) for p in (raw.get("deny_company") or [])],
        allow=[FilterPattern(**p) for p in (raw.get("allow") or [])],
        deny=[FilterPattern(**p) for p in (raw.get("deny") or [])],
    )


# ---------------------------------------------------------------------------
# Core matching
# ---------------------------------------------------------------------------


def _matches(pattern: FilterPattern, title: str) -> bool:
    """Return True if the pattern matches the (already-decoded) title."""
    if pattern.kind == "substring":
        return pattern.pattern.lower() in title.lower()
    # regex — always case-insensitive
    return bool(re.search(pattern.pattern, title, re.IGNORECASE))


def filter_title(
    title: str,
    company: str | None = None,
    filters: TitleFilters | None = None,
) -> FilterDecision:
    """Evaluate title (and optionally company) against filter tiers and return a FilterDecision.

    Evaluation order (4 tiers):
      1. pre_deny[]     — title-based, unconditional drop, no rescue possible
      2. deny_company[] — company-based, unconditional drop; skipped when company is None/empty
      3. allow[]        — title-based escape hatch from deny[]
      4. deny[]         — title-based default-drop

    Args:
        title:   The job title string (raw — HTML entities decoded internally).
        company: Optional company name string. When provided, deny_company patterns
                 are matched against it. Pass None (or omit) for backward compat.
        filters: Optional pre-loaded TitleFilters; loads from config file if None.

    Returns:
        FilterDecision with action='pass' or action='drop'.
    """
    if not title or not title.strip():
        # Empty / whitespace-only title: pass through, let downstream handle it.
        return FilterDecision(action="pass", matched_pattern=None, reason="empty title")

    # Decode HTML entities BEFORE pattern matching so titles like
    # "Data &amp; Analytics Engineer" match correctly.
    decoded = html.unescape(title)

    cfg = filters if filters is not None else load_filters(_DEFAULT_CONFIG_PATH)

    # 1. Pre-deny list — checked before allow; no rescue possible.
    #    Used for absolute disqualifiers (entry-level, etc.) that must drop even
    #    when an ML/Data allow pattern would otherwise rescue the title.
    for pd in cfg.pre_deny:
        if _matches(pd, decoded):
            logger.info(
                "title_filter: DROP (pre-deny) title=%r matched_pattern=%r",
                decoded,
                pd.pattern,
            )
            return FilterDecision(
                action="drop",
                matched_pattern=pd.pattern,
                reason=pd.note or pd.pattern,
            )

    # 2. Deny-company list — matched against company string, not title.
    #    Skipped entirely when company is None or empty string (backward compat).
    #    Hard-drop: no allow override can rescue these.
    if company:
        for dc in cfg.deny_company:
            if _matches(dc, company):
                logger.info(
                    "title_filter: DROP (deny-company) company=%r matched_pattern=%r",
                    company,
                    dc.pattern,
                )
                return FilterDecision(
                    action="drop",
                    matched_pattern=dc.pattern,
                    reason=dc.note or dc.pattern,
                )

    # 3. Allow list checked next — any match → unconditional pass.
    for ap in cfg.allow:
        if _matches(ap, decoded):
            logger.debug(
                "title_filter: PASS (allow override) title=%r pattern=%r",
                decoded,
                ap.pattern,
            )
            return FilterDecision(
                action="pass",
                matched_pattern=ap.pattern,
                reason=f"allow override: {ap.note}" if ap.note else "allow override",
            )

    # 4. Deny list — first match → drop.
    for dp in cfg.deny:
        if _matches(dp, decoded):
            logger.info(
                "title_filter: DROP title=%r matched_pattern=%r",
                decoded,
                dp.pattern,
            )
            return FilterDecision(
                action="drop",
                matched_pattern=dp.pattern,
                reason=dp.note or dp.pattern,
            )

    # 5. No tier matched → pass.
    logger.debug("title_filter: PASS (no deny match) title=%r", decoded)
    return FilterDecision(action="pass", matched_pattern=None, reason=None)


# ---------------------------------------------------------------------------
# CLI demo entry point
# ---------------------------------------------------------------------------


def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate a job title against the title deny/allow filter (C19)."
    )
    parser.add_argument("--title", required=True, help="Job title to evaluate")
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to title_filters.yaml (default: config/title_filters.yaml)",
    )
    args = parser.parse_args()

    cfg = load_filters(args.config)
    decision = filter_title(args.title, filters=cfg)

    if decision.action == "drop":
        print(f"DROP — matched pattern: {decision.matched_pattern} — reason: {decision.reason}")
    else:
        if decision.matched_pattern:
            print(f"PASS — allow override matched: {decision.matched_pattern}")
        else:
            print("PASS")


if __name__ == "__main__":
    _main()
