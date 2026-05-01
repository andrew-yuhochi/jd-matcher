"""Phase: merge — Canonical merge-apply (C29 + C30).

Merge is combined with dedup in phases/dedup.py (per-posting interleave).
This module exists as a named phase for future extraction or testing.
"""

from __future__ import annotations


def run(state: dict) -> dict:
    """Pass-through — merge logic is interleaved with dedup in phases/dedup.py."""
    return state
