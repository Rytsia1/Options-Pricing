"""Offline unit tests for :mod:`src.market_data`.

These tests deliberately avoid the network: yfinance calls are *not*
exercised here (the demo / a real run is the integration test).
Only :func:`src.market_data.historical_volatility` and its input
validation are covered.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.market_data import historical_volatility


# ---------------------------------------------------------------------- #
# A. Synthetic series with known volatility
# ---------------------------------------------------------------------- #
def test_constant_daily_log_returns_have_known_annualized_vol() -> None:
    """If log-returns are a constant ``c`` (std=0), sigma must be 0."""
    prices = pd.Series(
        np.exp(np.cumsum([0.01] * 50)),  # 1% log-return per day
        name="Close",
    )
    # The series above has constant 1% log-returns so std == 0.
    assert historical_volatility(prices) == 0.0


def test_known_synthetic_series_gives_expected_sigma() -> None:
    """Fixed seed, fixed length: deterministic sigma (sanity check)."""
    rng = np.random.default_rng(seed=123)
    # 252 daily log-returns drawn from N(0, 0.01^2)  ⇒  annualized sigma ≈ 0.01 * sqrt(252)
    log_rets = rng.normal(loc=0.0, scale=0.01, size=252)
    prices = pd.Series(np.exp(np.cumsum(log_rets)), name="Close")
    sigma = historical_volatility(prices, trading_days=252)
    assert sigma == pytest.approx(0.01, abs=5e-4)


def test_annualization_factor_scales_linearly() -> None:
    """Doubling trading_days multiplies sigma by sqrt(2)."""
    rng = np.random.default_rng(seed=42)
    log_rets = rng.normal(loc=0.0, scale=0.02, size=500)
    prices = pd.Series(np.exp(np.cumsum(log_rets)), name="Close")
    s1 = historical_volatility(prices, trading_days=252)
    s2 = historical_volatility(prices, trading_days=504)
    assert s2 == pytest.approx(s1 * math.sqrt(2.0), rel=1e-9)


# ---------------------------------------------------------------------- #
# B. Input validation
# ---------------------------------------------------------------------- #
def test_single_observation_raises() -> None:
    with pytest.raises(ValueError):
        historical_volatility(pd.Series([100.0], name="Close"))


def test_empty_series_raises() -> None:
    with pytest.raises(ValueError):
        historical_volatility(pd.Series([], dtype=float, name="Close"))


def test_non_positive_prices_raise() -> None:
    bad = pd.Series([100.0, 0.0, 105.0], name="Close")
    with pytest.raises(ValueError):
        historical_volatility(bad)


def test_invalid_trading_days_raises() -> None:
    prices = pd.Series([100.0, 101.0, 102.0], name="Close")
    with pytest.raises(ValueError):
        historical_volatility(prices, trading_days=0)


# ---------------------------------------------------------------------- #
# C. NaN handling
# ---------------------------------------------------------------------- #
def test_nan_prices_are_dropped() -> None:
    """NaN values should be dropped before computing log-returns."""
    clean = pd.Series(
        np.exp(np.cumsum([0.01, 0.01, 0.01, 0.01, 0.01])), name="Close",
    )
    dirty = clean.copy()
    dirty.iloc[1] = np.nan       # introduces a NaN in the middle
    # After dropping NaN, the *remaining* log-returns are still all 0.01
    # (because the NaN just makes one of the two adjacent return pairs
    # undefined; the others are unaffected). The standard deviation of a
    # constant series is 0.
    assert historical_volatility(dirty) == 0.0
