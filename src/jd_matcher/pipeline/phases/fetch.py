"""Phase: fetch — Gmail message retrieval (C3).

Implemented inline in pipeline/__init__.py _run_gmail_source() because fetch
and parse are tightly coupled via the per-email loop. This module exists as a
named phase entry so TASK-M3-* can reference it; the thin shim delegates back.
"""

from __future__ import annotations


def run(state: dict) -> dict:
    """Pass-through — fetch logic lives in the orchestrator's _run_gmail_source()."""
    return state
