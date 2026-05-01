"""Phase: filter — Title-based interest filter (C19).

C19 filtering runs inside _run_gmail_source() per-posting, immediately after
parsing. This module exists as a named phase for future extraction.
"""

from __future__ import annotations


def run(state: dict) -> dict:
    """Pass-through — C19 filter logic lives in the orchestrator's per-email loop."""
    return state
