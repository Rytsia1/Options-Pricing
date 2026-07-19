"""Black-Scholes-Merton (BSM) option pricing model.

This module provides the :class:`EuropeanOption` class, which computes the
theoretical price of a European call or put option using the closed-form
Black-Scholes-Merton formula.

The classic BSM formulas implemented here assume:
    * A constant risk-free rate ``r`` (continuous compounding).
    * A constant volatility ``sigma``.
    * No dividends paid on the underlying asset.
    * A frictionless market (no transaction costs, continuous trading).
    * Log-normal distribution of the underlying asset price at maturity.

References
----------
Black, F., & Scholes, M. (1973). "The Pricing of Options and Corporate
Liabilities". Journal of Political Economy, 81(3), 637-654.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from scipy.stats import norm


OptionType = Literal["call", "put"]


class EuropeanOption:
    """A European-style option priced with the Black-Scholes-Merton formula.

    Parameters
    ----------
    S : float
        Current spot price of the underlying asset. Must be positive.
    K : float
        Strike price of the option. Must be positive.
    T : float
        Time to maturity in years. Must be positive.
    r : float
        Continuously-compounded risk-free interest rate (e.g. ``0.05`` for 5%).
    sigma : float
        Volatility of the underlying asset's returns. Must be positive.
    option_type : {"call", "put"}
        Whether the option is a call (``"call"``) or a put (``"put"``).

    Attributes
    ----------
    S, K, T, r, sigma : float
        The pricing inputs, stored as validated floats.
    option_type : {"call", "put"}
        The option side.

    Examples
    --------
    >>> option = EuropeanOption(S=100, K=100, T=1, r=0.05, sigma=0.20, option_type="call")
    >>> round(option.price(), 4)
    10.4506
    """

    def __init__(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        option_type: OptionType,
    ) -> None:
        self._validate_inputs(S=S, K=K, T=T, sigma=sigma, option_type=option_type)

        self.S: float = float(S)
        self.K: float = float(K)
        self.T: float = float(T)
        self.r: float = float(r)
        self.sigma: float = float(sigma)
        self.option_type: OptionType = option_type

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def price(self) -> float:
        """Return the theoretical Black-Scholes-Merton price of the option.

        Returns
        -------
        float
            The option's present value under the BSM assumptions.
        """
        d1: float = self._d1()
        d2: float = self._d2(d1)
        discount: float = self._discount_factor()

        if self.option_type == "call":
            return self._call_price(d1, d2, discount)
        return self._put_price(d1, d2, discount)

    # ------------------------------------------------------------------ #
    # Black-Scholes-Merton components
    # ------------------------------------------------------------------ #
    def _d1(self) -> float:
        """Compute ``d1`` of the BSM formula."""
        return (
            np.log(self.S / self.K)
            + (self.r + 0.5 * self.sigma ** 2) * self.T
        ) / (self.sigma * np.sqrt(self.T))

    def _d2(self, d1: float) -> float:
        """Compute ``d2`` of the BSM formula given ``d1``."""
        return d1 - self.sigma * np.sqrt(self.T)

    def _discount_factor(self) -> float:
        """Present-value discount factor ``exp(-r * T)``."""
        return np.exp(-self.r * self.T)

    def _call_price(self, d1: float, d2: float, discount: float) -> float:
        """Closed-form BSM price of a European call."""
        return float(self.S * norm.cdf(d1) - self.K * discount * norm.cdf(d2))

    def _put_price(self, d1: float, d2: float, discount: float) -> float:
        """Closed-form BSM price of a European put."""
        return float(self.K * discount * norm.cdf(-d2) - self.S * norm.cdf(-d1))

    # ------------------------------------------------------------------ #
    # Input validation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _validate_inputs(
        *,
        S: float,
        K: float,
        T: float,
        sigma: float,
        option_type: str,
    ) -> None:
        """Validate the BSM pricing inputs and raise ``ValueError`` on bad data."""
        if S <= 0:
            raise ValueError(f"Spot price S must be positive, got {S}.")
        if K <= 0:
            raise ValueError(f"Strike price K must be positive, got {K}.")
        if T <= 0:
            raise ValueError(f"Time to maturity T must be positive, got {T}.")
        if sigma <= 0:
            raise ValueError(f"Volatility sigma must be positive, got {sigma}.")
        if option_type not in ("call", "put"):
            raise ValueError(
                f"option_type must be 'call' or 'put', got {option_type!r}."
            )

    def __repr__(self) -> str:
        return (
            f"EuropeanOption(S={self.S}, K={self.K}, T={self.T}, "
            f"r={self.r}, sigma={self.sigma}, option_type={self.option_type!r})"
        )
