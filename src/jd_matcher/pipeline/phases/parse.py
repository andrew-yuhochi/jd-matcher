"""Phase: parse — Email-to-posting parsing (C4).

Parsing is interleaved with fetch inside _run_gmail_source(). This module
exists as a named phase so TASK-M3-* can extend it independently if needed.
"""

from __future__ import annotations


def run(state: dict) -> dict:
    """Pass-through — parse logic lives in the orchestrator's _run_gmail_source()."""
    return state
