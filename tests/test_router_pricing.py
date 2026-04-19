from __future__ import annotations

import pytest

from compliance_workflow_demo.router.pricing import PRICES, cost_usd


def test_known_model_anthropic_haiku():
    # Haiku 4.5: $0.25 input, $1.25 output per 1M tokens.
    # 1M in + 1M out = 0.25 + 1.25 = 1.50
    actual = cost_usd("anthropic", "claude-haiku-4-5-20251001", 1_000_000, 1_000_000)
    assert actual == pytest.approx(1.50)


def test_known_model_openai_gpt4o_mini():
    # gpt-4o-mini: $0.15 input, $0.60 output per 1M tokens.
    # 500k in + 250k out = 0.075 + 0.15 = 0.225
    assert cost_usd("openai", "gpt-4o-mini", 500_000, 250_000) == pytest.approx(0.225)


def test_input_and_output_rates_are_not_transposed():
    # Asymmetric token counts make a transposition detectable: if rates were
    # swapped, charging 1M in (cheap) at the output rate would explode the cost.
    model = "claude-opus-4-7-20260401"
    in_rate, out_rate = PRICES[("anthropic", model)]
    assert in_rate < out_rate, "this test assumes input is cheaper than output"
    assert cost_usd("anthropic", model, 1_000_000, 0) == pytest.approx(in_rate)
    assert cost_usd("anthropic", model, 0, 1_000_000) == pytest.approx(out_rate)


def test_zero_tokens_zero_cost():
    assert cost_usd("openai", "gpt-4o", 0, 0) == 0.0


def test_unknown_pair_returns_none():
    # Contract: don't guess for unknown (provider, model) — surface as unknown
    # so the caller can decide (log, alert, store NULL) instead of silently
    # under-reporting cost.
    assert cost_usd("anthropic", "claude-future-99", 100, 100) is None
    assert cost_usd("mystery", "gpt-4o", 100, 100) is None


def test_all_table_entries_priced_consistently():
    # Sanity: every entry has positive rates and output >= input (true for
    # every commercial LLM today). Catches a typo'd row before it ships.
    for (provider, model), (in_rate, out_rate) in PRICES.items():
        assert in_rate > 0, f"{provider}/{model} input rate must be positive"
        assert out_rate >= in_rate, f"{provider}/{model} output rate < input rate looks wrong"
