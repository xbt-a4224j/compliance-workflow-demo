"""Per-model USD pricing for router cost accounting.

Static table — operators update when providers change pricing. Demo scope
only; production would pull from the provider's billing API or a
config file the ops team owns.
"""

from __future__ import annotations

# (provider, model) → (input_usd_per_mtok, output_usd_per_mtok)
PRICES: dict[tuple[str, str], tuple[float, float]] = {
    ("anthropic", "claude-haiku-4-5-20251001"):  (0.25,  1.25),
    ("anthropic", "claude-sonnet-4-5-20250929"): (3.00, 15.00),
    ("anthropic", "claude-opus-4-7-20260401"):   (15.00, 75.00),
    ("openai",    "gpt-4o-mini"):                (0.15,  0.60),
    ("openai",    "gpt-4o"):                     (2.50, 10.00),
    ("openai",    "gpt-4-turbo"):                (10.00, 30.00),
}


def cost_usd(provider: str, model: str, tokens_in: int, tokens_out: int) -> float | None:
    """Compute USD cost for a single call. Returns None if the (provider,
    model) pair isn't in the table — don't guess, surface it as unknown."""
    rates = PRICES.get((provider, model))
    if rates is None:
        return None
    in_rate, out_rate = rates
    return (tokens_in * in_rate + tokens_out * out_rate) / 1_000_000
