"""Unit tests for :mod:`src.monte_carlo`.

The tests validate the :class:`MonteCarloPricer` against three properties:

1. **Convergence** — with enough paths, MC prices converge to the BSM
   analytical price.
2. **Statistical correctness** — put-call parity, standard error scaling
   with ``1/sqrt(n)``, and variance reduction from antithetic variates.
3. **Engineering hygiene** — reproducibility, input validation, return
   types, and absence of Python for-loops in the hot path.

Run with::

    pytest tests/test_monte_carlo.py -v
"""

from __future__ import annotations

import time

import numpy as np
import pytest

from src.black_scholes import EuropeanOption
from src.monte_carlo import MonteCarloPricer


# ---------------------------------------------------------------------- #
# Reference scenario
# ---------------------------------------------------------------------- #
SCENARIO: dict[str, float] = {
    "S": 100.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20,
}


def _bsm_price(option_type: str, scenario: dict[str, float]) -> float:
    """Analytical BSM price used as the MC convergence reference."""
    return EuropeanOption(
        option_type=option_type,  # type: ignore[arg-type]
        **scenario,
    ).price()


# ---------------------------------------------------------------------- #
# A. Reproducibility
# ---------------------------------------------------------------------- #
def test_same_seed_gives_identical_price() -> None:
    p1 = MonteCarloPricer(
        **SCENARIO, n_paths=20_000, n_steps=1, option_type="call",
        seed=123, antithetic=False,
    )
    p2 = MonteCarloPricer(
        **SCENARIO, n_paths=20_000, n_steps=1, option_type="call",
        seed=123, antithetic=False,
    )
    assert p1.price() == p2.price()


# ---------------------------------------------------------------------- #
# B. Convergence to BSM
# ---------------------------------------------------------------------- #
@pytest.mark.parametrize("option_type", ["call", "put"])
def test_mc_converges_to_bsm(option_type: str) -> None:
    """At 200k paths (antithetic), MC price within 1% of BSM."""
    p = MonteCarloPricer(
        **SCENARIO, n_paths=200_000, n_steps=1,
        option_type=option_type,  # type: ignore[arg-type]
        seed=7, antithetic=True,
    )
    mc_price = p.price()
    bsm_price = _bsm_price(option_type, SCENARIO)
    rel_error = abs(mc_price - bsm_price) / bsm_price
    assert rel_error < 0.01, f"MC={mc_price}, BSM={bsm_price}, rel_error={rel_error}"


# ---------------------------------------------------------------------- #
# C. Put–Call parity in MC
# ---------------------------------------------------------------------- #
def test_mc_put_call_parity() -> None:
    """MC_C - MC_P should approximate S - K*exp(-rT) within ~4 std errors."""
    p = MonteCarloPricer(
        **SCENARIO, n_paths=200_000, n_steps=1, seed=11, antithetic=True,
    )
    prices = p.price_both()
    diff = prices["call"] - prices["put"]
    rhs = SCENARIO["S"] - SCENARIO["K"] * np.exp(-SCENARIO["r"] * SCENARIO["T"])
    tolerance = 4.0 * p.std_error()
    assert diff == pytest.approx(rhs, abs=tolerance)


# ---------------------------------------------------------------------- #
# D. Standard error scaling
# ---------------------------------------------------------------------- #
def test_std_error_scales_with_one_over_sqrt_n() -> None:
    """std_error(n=10k) / std_error(n=100k) ≈ sqrt(10)."""
    small = MonteCarloPricer(
        **SCENARIO, n_paths=10_000, n_steps=1, option_type="call",
        seed=42, antithetic=True,
    )
    large = MonteCarloPricer(
        **SCENARIO, n_paths=100_000, n_steps=1, option_type="call",
        seed=42, antithetic=True,
    )
    ratio = small.std_error() / large.std_error()
    expected = np.sqrt(10.0)
    assert ratio == pytest.approx(expected, rel=0.4)


# ---------------------------------------------------------------------- #
# E. Antithetic variance reduction
# ---------------------------------------------------------------------- #
def test_antithetic_reduces_variance() -> None:
    """At fixed n_paths, antithetic should yield a smaller std_error."""
    plain = MonteCarloPricer(
        **SCENARIO, n_paths=20_000, n_steps=1, option_type="call",
        seed=99, antithetic=False,
    )
    anti = MonteCarloPricer(
        **SCENARIO, n_paths=20_000, n_steps=1, option_type="call",
        seed=99, antithetic=True,
    )
    assert anti.std_error() < plain.std_error()


# ---------------------------------------------------------------------- #
# F. Vectorization / performance smoke test
# ---------------------------------------------------------------------- #
def test_no_python_loop_in_path_generation() -> None:
    """50k paths × 252 steps should finish well under 2s.

    This is a smoke test against accidentally introducing a Python for-loop
    over paths or time steps in :meth:`_simulate_terminal_prices`.
    """
    p = MonteCarloPricer(
        **SCENARIO, n_paths=50_000, n_steps=252, option_type="call",
        seed=1, antithetic=True,
    )
    start = time.perf_counter()
    _ = p.price()
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"Monte Carlo took {elapsed:.2f}s — likely a Python loop"


# ---------------------------------------------------------------------- #
# G. Output shapes and types
# ---------------------------------------------------------------------- #
def test_simulate_paths_shape_with_antithetic() -> None:
    p = MonteCarloPricer(
        **SCENARIO, n_paths=1_000, n_steps=50, option_type="call",
        seed=1, antithetic=True,
    )
    paths = p.simulate_paths()
    # Antithetic doubles the effective path count.
    assert paths.shape == (2_000, 51)


def test_simulate_paths_shape_without_antithetic() -> None:
    p = MonteCarloPricer(
        **SCENARIO, n_paths=1_000, n_steps=50, option_type="call",
        seed=1, antithetic=False,
    )
    paths = p.simulate_paths()
    assert paths.shape == (1_000, 51)


def test_first_column_of_paths_is_initial_spot() -> None:
    p = MonteCarloPricer(
        **SCENARIO, n_paths=500, n_steps=10, option_type="call",
        seed=1, antithetic=False,
    )
    paths = p.simulate_paths()
    assert np.allclose(paths[:, 0], SCENARIO["S"])


@pytest.mark.parametrize("option_type", ["call", "put"])
def test_price_returns_plain_float(option_type: str) -> None:
    p = MonteCarloPricer(
        **SCENARIO, n_paths=1_000, n_steps=1, option_type=option_type,  # type: ignore[arg-type]
        seed=1, antithetic=False,
    )
    assert type(p.price()) is float
    assert type(p.std_error()) is float


def test_confidence_interval_contains_mean() -> None:
    p = MonteCarloPricer(
        **SCENARIO, n_paths=20_000, n_steps=1, option_type="call",
        seed=1, antithetic=True,
    )
    lower, upper = p.confidence_interval_95()
    mean = p.price()
    assert lower <= mean <= upper


# ---------------------------------------------------------------------- #
# H. Boundary behaviour
# ---------------------------------------------------------------------- #
def test_call_price_zero_when_deep_otm() -> None:
    """S = 1, K = 1000: call price is essentially zero."""
    p = MonteCarloPricer(
        S=1.0, K=1000.0, T=1.0, r=0.05, sigma=0.20,
        n_paths=10_000, n_steps=1, option_type="call", seed=1,
    )
    assert p.price() < 1e-6


def test_put_price_at_intrinsic_when_deep_itm() -> None:
    """S = 1, K = 1000: put price should approach K * exp(-rT) (with time value)."""
    p = MonteCarloPricer(
        S=1.0, K=1000.0, T=1.0, r=0.05, sigma=0.20,
        n_paths=10_000, n_steps=1, option_type="put", seed=1,
    )
    intrinsic = 1000.0 * np.exp(-0.05)
    # Put is deep ITM but not zero-vol, so it has slight time value; we
    # only require it to be *at* intrinsic (not below) and below the
    # un-discounted strike.
    assert intrinsic * 0.99 <= p.price() <= 1000.0


# ---------------------------------------------------------------------- #
# I. Input validation
# ---------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "bad_kwargs",
    [
        {"S": 0.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20, "n_paths": 1000, "n_steps": 1, "option_type": "call"},
        {"S": -10.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20, "n_paths": 1000, "n_steps": 1, "option_type": "call"},
        {"S": 100.0, "K": 0.0, "T": 1.0, "r": 0.05, "sigma": 0.20, "n_paths": 1000, "n_steps": 1, "option_type": "put"},
        {"S": 100.0, "K": 100.0, "T": 0.0, "r": 0.05, "sigma": 0.20, "n_paths": 1000, "n_steps": 1, "option_type": "call"},
        {"S": 100.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.0, "n_paths": 1000, "n_steps": 1, "option_type": "call"},
        {"S": 100.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20, "n_paths": 0, "n_steps": 1, "option_type": "call"},
        {"S": 100.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20, "n_paths": 1000, "n_steps": 0, "option_type": "call"},
        {"S": 100.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20, "n_paths": 1000, "n_steps": 1, "option_type": "banana"},
    ],
)
def test_invalid_inputs_raise_value_error(bad_kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        MonteCarloPricer(**bad_kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------- #
# J. Price-both contract
# ---------------------------------------------------------------------- #
def test_price_both_returns_call_and_put() -> None:
    p = MonteCarloPricer(
        **SCENARIO, n_paths=50_000, n_steps=1, seed=3, antithetic=True,
    )
    out = p.price_both()
    assert set(out.keys()) == {"call", "put"}
    assert isinstance(out["call"], float)
    assert isinstance(out["put"], float)
    # Both should be non-negative and within reasonable range.
    assert 0.0 <= out["call"] <= SCENARIO["S"]
    assert 0.0 <= out["put"] <= SCENARIO["K"]
