"""Cost-estimation helper: rate lookup, fallback, and the cached-read split."""

import pytest

from copilot.pricing import DEFAULT_MODEL, estimate_cost, rates_for


def test_opus_matches_published_rates():
    # 1M input, 1M cached, 1M output on opus = 5 + 0.5 + 25.
    assert estimate_cost(1_000_000, 1_000_000, 1_000_000, "claude-opus-4-8") == pytest.approx(30.5)


def test_haiku_is_cheaper_than_opus():
    args = (1_000_000, 0, 1_000_000)
    assert estimate_cost(*args, "claude-haiku-4-5") < estimate_cost(*args, "claude-opus-4-8")


def test_cached_reads_bill_at_lower_rate():
    same_tokens = 1_000_000
    cached_cost = estimate_cost(0, same_tokens, 0, "claude-opus-4-8")
    uncached_cost = estimate_cost(same_tokens, 0, 0, "claude-opus-4-8")
    assert cached_cost == pytest.approx(0.5)
    assert cached_cost < uncached_cost


def test_zero_tokens_is_free():
    assert estimate_cost(0, 0, 0) == 0.0


def test_unknown_model_falls_back_to_default():
    assert rates_for("some-unreleased-model") == rates_for(DEFAULT_MODEL)


def test_dated_alias_matches_by_prefix():
    # e.g. a dated suffix should resolve to the base model's rates.
    assert rates_for("claude-haiku-4-5-20251001") == rates_for("claude-haiku-4-5")
