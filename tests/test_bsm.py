"""Unit tests for :mod:`src.black_scholes`.

The tests in this module validate the closed-form Black-Scholes-Merton
formulas and their derived Greeks against a set of well-known reference
values, structural properties (put-call parity, gamma/vega symmetry),
and a collection of edge cases (very short maturity, deep ITM, deep OTM).

Run with::

    pytest -v
"""

from __future__ import annotations

import math

import pytest

from src.black_scholes import EuropeanOption


# ---------------------------------------------------------------------- #
# Reference scenarios
# ---------------------------------------------------------------------- #
# Each scenario is a (S, K, T, r, sigma) tuple. Reference values for the
# price and the Greeks are computed from the closed-form BSM formulas and
# cross-checked against a reference implementation / standard textbook
# numbers. They are stated to 4 decimal places here to keep the test
# tolerances tight while tolerating floating-point rounding.
# ---------------------------------------------------------------------- #
SCENARIO_STANDARD: dict[str, float] = {
    "S": 100.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20,
}
SCENARIO_MID: dict[str, float] = {
    "S": 100.0, "K": 100.0, "T": 0.5, "r": 0.10, "sigma": 0.30,
}
SCENARIO_LOW_S: dict[str, float] = {
    "S": 50.0, "K": 60.0, "T": 2.0, "r": 0.02, "sigma": 0.25,
}


def _expected_call_price(s: dict[str, float]) -> float:
    """Closed-form BSM call price used as the test oracle."""
    from scipy.stats import norm

    d1 = (math.log(s["S"] / s["K"]) + (s["r"] + 0.5 * s["sigma"] ** 2) * s["T"]) / (
        s["sigma"] * math.sqrt(s["T"])
    )
    d2 = d1 - s["sigma"] * math.sqrt(s["T"])
    return s["S"] * norm.cdf(d1) - s["K"] * math.exp(-s["r"] * s["T"]) * norm.cdf(d2)


def _expected_put_price(s: dict[str, float]) -> float:
    """Closed-form BSM put price used as the test oracle."""
    from scipy.stats import norm

    d1 = (math.log(s["S"] / s["K"]) + (s["r"] + 0.5 * s["sigma"] ** 2) * s["T"]) / (
        s["sigma"] * math.sqrt(s["T"])
    )
    d2 = d1 - s["sigma"] * math.sqrt(s["T"])
    return s["K"] * math.exp(-s["r"] * s["T"]) * norm.cdf(-d2) - s["S"] * norm.cdf(-d1)


# ---------------------------------------------------------------------- #
# A. Price validation against textbook values
# ---------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "scenario, expected_call, expected_put",
    [
        # Standard Hull / BSM textbook example
        (SCENARIO_STANDARD, 10.4506, 5.5705),
        # Mid-volatility, higher rate, half-year
        (SCENARIO_MID, 8.8587, 4.1840),
        # Out-of-the-money, low spot, long maturity
        (SCENARIO_LOW_S, 4.2879, 11.8570),
    ],
)
def test_prices_match_textbook(
    scenario: dict[str, float], expected_call: float, expected_put: float
) -> None:
    call = EuropeanOption(option_type="call", **scenario)
    put = EuropeanOption(option_type="put", **scenario)
    assert call.price() == pytest.approx(expected_call, abs=5e-4)
    assert put.price() == pytest.approx(expected_put, abs=5e-4)


@pytest.mark.parametrize("scenario", [SCENARIO_STANDARD, SCENARIO_MID, SCENARIO_LOW_S])
def test_call_and_put_match_independent_oracle(scenario: dict[str, float]) -> None:
    """The class's call/put prices must match the same closed-form oracle."""
    call = EuropeanOption(option_type="call", **scenario)
    put = EuropeanOption(option_type="put", **scenario)
    assert call.price() == pytest.approx(_expected_call_price(scenario), rel=1e-10)
    assert put.price() == pytest.approx(_expected_put_price(scenario), rel=1e-10)


# ---------------------------------------------------------------------- #
# B. Put–Call parity
# ---------------------------------------------------------------------- #
@pytest.mark.parametrize("scenario", [SCENARIO_STANDARD, SCENARIO_MID, SCENARIO_LOW_S])
def test_put_call_parity(scenario: dict[str, float]) -> None:
    """C - P = S - K * exp(-r * T)   (no dividends, European)."""
    call = EuropeanOption(option_type="call", **scenario)
    put = EuropeanOption(option_type="put", **scenario)
    rhs = scenario["S"] - scenario["K"] * math.exp(-scenario["r"] * scenario["T"])
    assert (call.price() - put.price()) == pytest.approx(rhs, abs=1e-10)


# ---------------------------------------------------------------------- #
# C. Greek validation — structural properties
# ---------------------------------------------------------------------- #
@pytest.mark.parametrize("scenario", [SCENARIO_STANDARD, SCENARIO_MID, SCENARIO_LOW_S])
def test_delta_is_in_unit_interval(scenario: dict[str, float]) -> None:
    call = EuropeanOption(option_type="call", **scenario)
    put = EuropeanOption(option_type="put", **scenario)
    assert 0.0 <= call.delta() <= 1.0
    assert -1.0 <= put.delta() <= 0.0


@pytest.mark.parametrize("scenario", [SCENARIO_STANDARD, SCENARIO_MID, SCENARIO_LOW_S])
def test_delta_call_minus_one_equals_delta_put(scenario: dict[str, float]) -> None:
    """Put-Call delta parity: Delta_call - Delta_put = 1."""
    call = EuropeanOption(option_type="call", **scenario)
    put = EuropeanOption(option_type="put", **scenario)
    assert (call.delta() - put.delta()) == pytest.approx(1.0, abs=1e-12)


@pytest.mark.parametrize("scenario", [SCENARIO_STANDARD, SCENARIO_MID, SCENARIO_LOW_S])
def test_gamma_and_vega_identical_for_call_and_put(scenario: dict[str, float]) -> None:
    """Gamma and Vega are identical for a European call and put."""
    call = EuropeanOption(option_type="call", **scenario)
    put = EuropeanOption(option_type="put", **scenario)
    assert call.gamma() == pytest.approx(put.gamma(), abs=1e-12)
    assert call.vega() == pytest.approx(put.vega(), abs=1e-12)


@pytest.mark.parametrize("scenario", [SCENARIO_STANDARD, SCENARIO_MID, SCENARIO_LOW_S])
def test_gamma_and_vega_are_positive(scenario: dict[str, float]) -> None:
    call = EuropeanOption(option_type="call", **scenario)
    assert call.gamma() > 0.0
    assert call.vega() > 0.0


@pytest.mark.parametrize("scenario", [SCENARIO_STANDARD, SCENARIO_MID, SCENARIO_LOW_S])
def test_rho_signs(scenario: dict[str, float]) -> None:
    """Rho > 0 for calls, < 0 for puts."""
    call = EuropeanOption(option_type="call", **scenario)
    put = EuropeanOption(option_type="put", **scenario)
    assert call.rho() > 0.0
    assert put.rho() < 0.0


# ---------------------------------------------------------------------- #
# D. Greek validation — closed-form reference values
# ---------------------------------------------------------------------- #
def test_call_greeks_match_textbook() -> None:
    """Standard scenario Call Greeks vs. textbook reference values."""
    call = EuropeanOption(option_type="call", **SCENARIO_STANDARD)
    assert call.delta() == pytest.approx(0.636831, abs=5e-6)
    assert call.gamma() == pytest.approx(0.018762, abs=5e-6)
    assert call.vega() == pytest.approx(37.5240, abs=5e-3)
    assert call.theta() == pytest.approx(-6.4143, abs=5e-4)
    assert call.rho() == pytest.approx(53.2325, abs=5e-4)


def test_put_greeks_match_textbook() -> None:
    """Standard scenario Put Greeks vs. textbook reference values."""
    put = EuropeanOption(option_type="put", **SCENARIO_STANDARD)
    assert put.delta() == pytest.approx(-0.363169, abs=5e-6)
    assert put.gamma() == pytest.approx(0.018762, abs=5e-6)
    assert put.vega() == pytest.approx(37.5240, abs=5e-3)
    assert put.theta() == pytest.approx(-1.6579, abs=5e-4)
    assert put.rho() == pytest.approx(-41.8905, abs=5e-4)


def test_greeks_dict_contains_all_five() -> None:
    """`greeks()` returns all five Greeks with correct types."""
    call = EuropeanOption(option_type="call", **SCENARIO_STANDARD)
    g = call.greeks()
    assert set(g.keys()) == {"delta", "gamma", "vega", "theta", "rho"}
    for value in g.values():
        assert isinstance(value, float)


# ---------------------------------------------------------------------- #
# E. Greeks via numerical differentiation
# ---------------------------------------------------------------------- #
def test_gamma_matches_numerical_second_derivative() -> None:
    """Gamma ≈ (V(S+h) - 2 V(S) + V(S-h)) / h^2."""
    s = SCENARIO_STANDARD
    h = 0.01
    call = EuropeanOption(option_type="call", **s)
    base = call.price()
    up = EuropeanOption(S=s["S"] + h, **{k: v for k, v in s.items() if k != "S"},
                        option_type="call").price()
    down = EuropeanOption(S=s["S"] - h, **{k: v for k, v in s.items() if k != "S"},
                          option_type="call").price()
    numerical_gamma = (up - 2 * base + down) / (h * h)
    assert call.gamma() == pytest.approx(numerical_gamma, rel=1e-3)


def test_delta_matches_numerical_first_derivative() -> None:
    """Delta ≈ (V(S+h) - V(S-h)) / (2 h)."""
    s = SCENARIO_STANDARD
    h = 0.01
    call = EuropeanOption(option_type="call", **s)
    up = EuropeanOption(S=s["S"] + h, **{k: v for k, v in s.items() if k != "S"},
                        option_type="call").price()
    down = EuropeanOption(S=s["S"] - h, **{k: v for k, v in s.items() if k != "S"},
                          option_type="call").price()
    numerical_delta = (up - down) / (2 * h)
    assert call.delta() == pytest.approx(numerical_delta, abs=1e-4)


# ---------------------------------------------------------------------- #
# F. Edge cases
# ---------------------------------------------------------------------- #
def test_deep_itm_call() -> None:
    """Deep ITM call: delta → 1, call price → S - K * exp(-rT)."""
    deep_itm = {"S": 200.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20}
    call = EuropeanOption(option_type="call", **deep_itm)
    intrinsic = deep_itm["S"] - deep_itm["K"] * math.exp(-deep_itm["r"] * deep_itm["T"])
    assert call.delta() == pytest.approx(1.0, abs=1e-4)
    assert call.gamma() == pytest.approx(0.0, abs=1e-4)
    assert call.vega() == pytest.approx(0.0, abs=1e-3)
    assert call.price() == pytest.approx(intrinsic, abs=1e-3)


def test_deep_otm_call() -> None:
    """Deep OTM call: delta → 0, price is very small but positive."""
    deep_otm = {"S": 50.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20}
    call = EuropeanOption(option_type="call", **deep_otm)
    assert call.delta() == pytest.approx(0.0, abs=1e-2)
    assert 0.0 <= call.price() <= 0.05


def test_very_short_maturity() -> None:
    """T = 1/365: prices stay finite and non-negative, delta ∈ [0, 1]."""
    short = {"S": 100.0, "K": 100.0, "T": 1.0 / 365.0, "r": 0.05, "sigma": 0.20}
    call = EuropeanOption(option_type="call", **short)
    put = EuropeanOption(option_type="put", **short)
    # Intrinsic cap: at-the-money, time value is small but positive for call.
    assert 0.0 <= call.price() <= 1.0
    assert 0.0 <= put.price() <= 1.0
    assert 0.0 <= call.delta() <= 1.0
    assert -1.0 <= put.delta() <= 0.0
    # Put-call parity still holds.
    rhs = short["S"] - short["K"] * math.exp(-short["r"] * short["T"])
    assert (call.price() - put.price()) == pytest.approx(rhs, abs=1e-10)


def test_put_as_s_goes_to_zero() -> None:
    """As S → 0+, put delta → -1 and put price → K * exp(-rT)."""
    tiny_s = {"S": 1e-6, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20}
    put = EuropeanOption(option_type="put", **tiny_s)
    upper_bound = tiny_s["K"] * math.exp(-tiny_s["r"] * tiny_s["T"])
    assert put.delta() == pytest.approx(-1.0, abs=1e-3)
    assert put.price() == pytest.approx(upper_bound, rel=1e-3)


# ---------------------------------------------------------------------- #
# G. Input validation
# ---------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {"S": 0.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20, "option_type": "call"},
        {"S": -10.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20, "option_type": "call"},
        {"S": 100.0, "K": 0.0, "T": 1.0, "r": 0.05, "sigma": 0.20, "option_type": "put"},
        {"S": 100.0, "K": 100.0, "T": 0.0, "r": 0.05, "sigma": 0.20, "option_type": "call"},
        {"S": 100.0, "K": 100.0, "T": -1.0, "r": 0.05, "sigma": 0.20, "option_type": "call"},
        {"S": 100.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.0, "option_type": "call"},
        {"S": 100.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": -0.1, "option_type": "call"},
        {"S": 100.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20, "option_type": "banana"},
    ],
)
def test_invalid_inputs_raise_value_error(bad_kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        EuropeanOption(**bad_kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------- #
# H. Return-type contract
# ---------------------------------------------------------------------- #
@pytest.mark.parametrize("option_type", ["call", "put"])
def test_price_and_greeks_return_plain_float(option_type: str) -> None:
    """All public methods return ``float``, not ``numpy.float64``."""
    opt = EuropeanOption(option_type=option_type, **SCENARIO_STANDARD)  # type: ignore[arg-type]
    for value in (opt.price(), opt.delta(), opt.gamma(), opt.vega(),
                  opt.theta(), opt.rho()):
        assert type(value) is float
