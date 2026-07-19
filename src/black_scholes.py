"""Black-Scholes-Merton (BSM) option pricing model.

This module provides the :class:`EuropeanOption` class, which computes the
theoretical price and the full set of first- and second-order Greeks
(Delta, Gamma, Vega, Theta, Rho) of a European call or put option using
the closed-form Black-Scholes-Merton formulas.

The classic BSM formulas implemented here assume:
    * A constant risk-free rate ``r`` (continuous compounding).
    * A constant volatility ``sigma``.
    * No dividends paid on the underlying asset.
    * A frictionless market (no transaction costs, continuous trading).
    * Log-normal distribution of the underlying asset price at maturity.

Conventions for the Greeks
--------------------------
All Greeks are returned with respect to the natural change units of the
underlying BSM model:

* **Delta**: per 1.0 change in spot ``S``.
* **Gamma**: per (1.0)² change in spot ``S``.
* **Vega**: per 1.0 (i.e. 100%) change in volatility ``sigma``.
* **Theta**: per 1 year of calendar time. Divide by 365 (or 252) for
  per-calendar-day decay.
* **Rho**: per 1.0 (i.e. 100%) change in the rate ``r``.

References
----------
Black, F., & Scholes, M. (1973). "The Pricing of Options and Corporate
Liabilities". Journal of Political Economy, 81(3), 637-654.

Hull, J. C. (2017). "Options, Futures, and Other Derivatives" (10th ed.).
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
    >>> g = option.greeks()
    >>> round(g["delta"], 4), round(g["gamma"], 4), round(g["vega"], 4)
    (0.6368, 0.0188, 37.524)
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
    # Public API — pricing
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
    # Public API — Greeks
    # ------------------------------------------------------------------ #
    def delta(self) -> float:
        """Return the option's Delta (``∂V/∂S``)."""
        d1: float = self._d1()
        if self.option_type == "call":
            return self._delta_call(d1)
        return self._delta_put(d1)

    def gamma(self) -> float:
        """Return the option's Gamma (``∂²V/∂S²``).

        Gamma is identical for a European call and put sharing the same
        inputs.
        """
        return self._gamma()

    def vega(self) -> float:
        """Return the option's Vega (``∂V/∂σ``) per unit change in volatility.

        Returned per 1.0 (= 100%) change in ``sigma``. Identical for call
        and put.
        """
        return self._vega()

    def theta(self) -> float:
        """Return the option's Theta (``∂V/∂T``) per year of calendar time."""
        d1: float = self._d1()
        d2: float = self._d2(d1)
        discount: float = self._discount_factor()
        n_d1: float = self._n_d1(d1)

        if self.option_type == "call":
            return self._theta_call(d1, d2, discount, n_d1)
        return self._theta_put(d1, d2, discount, n_d1)

    def rho(self) -> float:
        """Return the option's Rho (``∂V/∂r``) per unit change in rate.

        Returned per 1.0 (= 100%) change in ``r``.
        """
        d1: float = self._d1()
        d2: float = self._d2(d1)
        discount: float = self._discount_factor()

        if self.option_type == "call":
            return self._rho_call(d2, discount)
        return self._rho_put(d2, discount)

    def greeks(self) -> dict[str, float]:
        """Return all five Greeks as a dictionary.

        Returns
        -------
        dict[str, float]
            Mapping with keys ``"delta"``, ``"gamma"``, ``"vega"``,
            ``"theta"``, ``"rho"``.
        """
        return {
            "delta": self.delta(),
            "gamma": self.gamma(),
            "vega": self.vega(),
            "theta": self.theta(),
            "rho": self.rho(),
        }

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

    def _n_d1(self, d1: float) -> float:
        """Standard normal PDF evaluated at ``d1`` (``n(d1)``)."""
        return float(norm.pdf(d1))

    def _discount_factor(self) -> float:
        """Present-value discount factor ``exp(-r * T)``."""
        return float(np.exp(-self.r * self.T))

    def _call_price(self, d1: float, d2: float, discount: float) -> float:
        """Closed-form BSM price of a European call."""
        return float(self.S * norm.cdf(d1) - self.K * discount * norm.cdf(d2))

    def _put_price(self, d1: float, d2: float, discount: float) -> float:
        """Closed-form BSM price of a European put."""
        return float(self.K * discount * norm.cdf(-d2) - self.S * norm.cdf(-d1))

    # ------------------------------------------------------------------ #
    # Closed-form Greeks (per-side helpers)
    # ------------------------------------------------------------------ #
    def _delta_call(self, d1: float) -> float:
        return float(norm.cdf(d1))

    def _delta_put(self, d1: float) -> float:
        return float(norm.cdf(d1) - 1.0)

    def _gamma(self) -> float:
        d1: float = self._d1()
        n_d1: float = self._n_d1(d1)
        return float(n_d1 / (self.S * self.sigma * np.sqrt(self.T)))

    def _vega(self) -> float:
        d1: float = self._d1()
        n_d1: float = self._n_d1(d1)
        return float(self.S * n_d1 * np.sqrt(self.T))

    def _theta_call(
        self, d1: float, d2: float, discount: float, n_d1: float
    ) -> float:
        return float(
            -self.S * n_d1 * self.sigma / (2.0 * np.sqrt(self.T))
            - self.r * self.K * discount * norm.cdf(d2)
        )

    def _theta_put(
        self, d1: float, d2: float, discount: float, n_d1: float
    ) -> float:
        return float(
            -self.S * n_d1 * self.sigma / (2.0 * np.sqrt(self.T))
            + self.r * self.K * discount * norm.cdf(-d2)
        )

    def _rho_call(self, d2: float, discount: float) -> float:
        return float(self.K * self.T * discount * norm.cdf(d2))

    def _rho_put(self, d2: float, discount: float) -> float:
        return float(-self.K * self.T * discount * norm.cdf(-d2))

    # ------------------------------------------------------------------ #
    # Input validation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _validate_inputs(**kwargs: object) -> None:
        """Validate the BSM pricing inputs and raise ``ValueError`` on bad data.

        Accepts the BSM inputs as keyword arguments (``S``, ``K``, ``T``,
        ``sigma``, ``option_type``) so the constructor can pass them
        through unchanged. The runtime contract is documented on
        :meth:`__init__`.
        """
        S = kwargs["S"]
        K = kwargs["K"]
        T = kwargs["T"]
        sigma = kwargs["sigma"]
        option_type = kwargs["option_type"]

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
