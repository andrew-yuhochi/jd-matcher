"""Phase: hydrate — JD hydration (C5).

Hydration runs in _run_hydrator_source(). This module exists as a named phase
for future extraction into a fully self-contained run() contract.
"""

from __future__ import annotations


def run(state: dict) -> dict:
    """Pass-through — hydration logic lives in the orchestrator's _run_hydrator_source()."""
    return state
