"""Per-model pricing for cost computation in llm_call_ledger.

PRICING (as_of 2026-04-27, source: https://openai.com/api/pricing/):
  - gpt-4o-mini: $0.15 / $0.60 per 1M input/output tokens
      = $0.00015 / $0.00060 per 1k tokens
  - text-embedding-3-small: $0.02 per 1M tokens
      = $0.00002 per 1k tokens

Update this table — and the as_of_date field — whenever OpenAI publishes
pricing changes.  The M3 cloud-vs-local benchmark sub-task reads costs from
llm_call_ledger rows which are computed here, so stale prices produce stale
benchmark totals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelPricing:
    model: str
    input_cost_per_1k: float
    output_cost_per_1k: float | None  # None for embedding models (no output tokens)
    as_of_date: str  # ISO-8601 date when these prices were last verified


PRICING_TABLE: dict[str, ModelPricing] = {
    "gpt-4o-mini": ModelPricing(
        model="gpt-4o-mini",
        input_cost_per_1k=0.00015,
        output_cost_per_1k=0.00060,
        as_of_date="2026-04-27",
    ),
    "text-embedding-3-small": ModelPricing(
        model="text-embedding-3-small",
        input_cost_per_1k=0.00002,
        output_cost_per_1k=None,
        as_of_date="2026-04-27",
    ),
}


def compute_cost(model: str, input_tokens: int, output_tokens: int = 0) -> float:
    """Return the USD cost for a single provider call.

    Returns 0.0 for unknown models (logs a warning so the gap is visible).
    """
    pricing = PRICING_TABLE.get(model)
    if pricing is None:
        logger.warning("pricing: unknown model '%s' — cost recorded as $0.00", model)
        return 0.0
    cost = (input_tokens / 1000) * pricing.input_cost_per_1k
    if pricing.output_cost_per_1k is not None and output_tokens:
        cost += (output_tokens / 1000) * pricing.output_cost_per_1k
    return cost
