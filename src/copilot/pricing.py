"""Token-cost estimation, shared by the dashboard and `copilot doctor`.

Kept in one place so the per-MTok numbers can't drift between the CLI and the
dashboard. Prices are USD per million tokens; cached input reads bill at ~0.1x
the normal input rate. ``input_tokens`` from a run is the UNCACHED remainder, so
cached reads are priced separately and added on.
"""

from __future__ import annotations

# model -> (input $/MTok, cached-input $/MTok, output $/MTok)
PRICING: dict[str, tuple[float, float, float]] = {
    "claude-opus-4-8": (
        5.0, 0.5, 25.0
        ),
    "claude-sonnet-4-6": (
        3.0, 0.3, 15.0
        ),
    "claude-haiku-4-5": (
        1.0, 0.1, 5.0
        ),
}

# Used when a model id isn't in the table (e.g. a dated/aliased variant).
DEFAULT_MODEL = "claude-opus-4-8"


def rates_for(model: str) -> tuple[float, float, float]:
    """Per-MTok (input, cached, output) rates for a model, with prefix fallback."""
    if model in PRICING:
        return PRICING[model]

    for known, rates in PRICING.items():
        if model.startswith(known):
            return rates

    return PRICING[DEFAULT_MODEL]


def estimate_cost(
    input_tokens: int,
    cached_tokens: int,
    output_tokens: int,
    model: str = DEFAULT_MODEL,
) -> float:
    """Estimated USD cost of a run (or summed runs) for the given model."""
    in_rate, cached_rate, out_rate = rates_for(model)

    return (
        input_tokens / 1e6 * in_rate
        + cached_tokens / 1e6 * cached_rate
        + output_tokens / 1e6 * out_rate
    )
