"""Phase: parse — Email-to-posting parsing (C4).

Parsing is interleaved with fetch inside run_gmail_source() in the fetch phase.
The per-email parse loop cannot be cleanly separated from the URL-dedup write
without introducing a stateful intermediate buffer, which adds complexity with
no PoC benefit. Both fetch and parse share the same SourceResult output.

This module exists as a named phase so TASK-M3-* can reference it independently
if a future refactor decouples them.
"""

from __future__ import annotations


def run(state: dict) -> dict:
    """Pass-through — parse logic lives in fetch.run_gmail_source()."""
    return state
