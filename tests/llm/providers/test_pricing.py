"""AC #6 — Pricing table and cost computation."""

from __future__ import annotations

import pytest

from jd_matcher.llm.providers.pricing import (
    PRICING_TABLE,
    ModelPricing,
    compute_cost,
)


def test_pricing_table_has_gpt4o_mini():
    assert "gpt-4o-mini" in PRICING_TABLE


def test_pricing_table_has_embedding_model():
    assert "text-embedding-3-small" in PRICING_TABLE


def test_model_pricing_fields():
    p = PRICING_TABLE["gpt-4o-mini"]
    assert isinstance(p, ModelPricing)
    assert p.input_cost_per_1k > 0
    assert p.output_cost_per_1k is not None and p.output_cost_per_1k > 0
    assert p.as_of_date  # non-empty ISO date string


def test_embedding_pricing_no_output_cost():
    p = PRICING_TABLE["text-embedding-3-small"]
    assert p.output_cost_per_1k is None


def test_compute_cost_gpt4o_mini():
    """1k input + 200 output gpt-4o-mini = $0.00015 + $0.00012 = $0.00027."""
    cost = compute_cost("gpt-4o-mini", input_tokens=1000, output_tokens=200)
    assert abs(cost - 0.00027) < 1e-9


def test_compute_cost_embedding():
    """1k input text-embedding-3-small = $0.00002."""
    cost = compute_cost("text-embedding-3-small", input_tokens=1000)
    assert abs(cost - 0.00002) < 1e-9


def test_compute_cost_unknown_model_returns_zero():
    cost = compute_cost("unknown-model-xyz", input_tokens=1000, output_tokens=500)
    assert cost == 0.0


def test_compute_cost_zero_tokens():
    cost = compute_cost("gpt-4o-mini", input_tokens=0, output_tokens=0)
    assert cost == 0.0
