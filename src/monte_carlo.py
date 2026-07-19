"""Monte Carlo option pricing under Geometric Brownian Motion (GBM).

This module provides the :class:`MonteCarloPricer` class, which prices
European calls and puts by Monte Carlo simulation of the risk-neutral
GBM dynamics of the underlying asset::

    dS_t = r * S_t * dt + sigma * S_t * dW_t

The simulation is **fully vectorized** with NumPy: all random normals are
drawn in a single :func:`numpy.random.Generator.standard_normal` call, and
path construction uses :func:`numpy.cumsum` and array broadcasting. There
are **no pure-Python for-loops** in path generation.

Variance reduction
------------------
The pricer supports **antithetic variates** (off by default for
backwards-compatibility, but recommended in practice). When enabled, each
random draw ``Z`` is paired with ``-Z``; this roughly halves the variance
of the estimator at no extra random-number cost.

Conventions
-----------
* Discounting is done with the continuously-compounded rate ``r``.
* The estimated price is the *discounted expected payoff*::

      price = exp(-r * T) * E[ payoff(S_T) ]

* The standard error and 95% confidence interval are also reported.

References
----------
Glasserman, P. (2003). "Monte Carlo Methods in Financial Engineering".
Springer.
"""

from __future__ import annotations

from typing import Literal, Optional

import numpy as np


OptionType = Literal["call", "put"]


class MonteCarloPricer:
    """Price a European option with a vectorized Monte Carlo simulation.

    Parameters
    ----------
    S : float
        Current spot price of the underlying asset. Must be positive.
    K : float
        Strike price of the option. Must be positive.
    T : float
        Time to maturity in years. Must be positive.
    r : float
        Continuously-compounded risk-free interest rate.
    sigma : float
        Volatility of the underlying asset's returns. Must be positive.
    n_paths : int
        Number of Monte Carlo scenarios. Defaults to 100 000.
    n_steps : int
        Number of time steps per path. For a European payoff only the
        terminal price matters, so the default of ``1`` produces the
        exact lognormal draw and matches the analytical BSM distribution.
        Use a larger value (e.g. ``252``) if you need the full simulated
        path.
    option_type : {"call", "put"}
        Whether to price a call or a put.
    seed : int, optional
        Random seed for reproducibility. If ``None`` (default), the
        results vary between runs.
    antithetic : bool
        If ``True``, pair each draw ``Z`` with ``-Z`` to reduce variance
        (recommended).

    Attributes
    ----------
    S, K, T, r, sigma : float
        The pricing inputs.
    n_paths, n_steps : int
        Simulation parameters.
    option_type : {"call", "put"}
        Option side.
    seed : int or None
        RNG seed in use.
    antithetic : bool
        Whether antithetic variates are enabled.

    Examples
    --------
    >>> import numpy as np
    >>> pricer = MonteCarloPricer(
    ...     S=100, K=100, T=1, r=0.05, sigma=0.20,
    ...     n_paths=50_000, n_steps=1, seed=42, antithetic=True,
    ...     option_type="call",
    ... )
    >>> round(pricer.price(), 4)
    10.45
    """

    def __init__(
        self,
        S: float,
        K: float,
        T: float,
        r: float,
        sigma: float,
        n_paths: int = 100_000,
        n_steps: int = 1,
        option_type: OptionType = "call",
        seed: Optional[int] = None,
        antithetic: bool = False,
    ) -> None:
        self._validate_inputs(
            S=S, K=K, T=T, sigma=sigma,
            n_paths=n_paths, n_steps=n_steps,
            option_type=option_type,
        )

        self.S: float = float(S)
        self.K: float = float(K)
        self.T: float = float(T)
        self.r: float = float(r)
        self.sigma: float = float(sigma)
        self.n_paths: int = int(n_paths)
        self.n_steps: int = int(n_steps)
        self.option_type: OptionType = option_type
        self.seed: Optional[int] = seed
        self.antithetic: bool = bool(antithetic)

        # Build a dedicated RNG so we don't perturb the global numpy state.
        self._rng: np.random.Generator = np.random.default_rng(seed)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def price(self) -> float:
        """Return the Monte Carlo estimate of the option price.

        Returns
        -------
        float
            Discounted expected payoff under the risk-neutral measure.
        """
        discounted_payoffs = self._discounted_payoffs()
        return float(np.mean(discounted_payoffs))

    def std_error(self) -> float:
        """Return the standard error of the Monte Carlo price estimate."""
        return float(np.std(self._discounted_payoffs(), ddof=1) / np.sqrt(self._n_eff))

    def confidence_interval_95(self) -> tuple[float, float]:
        """Return the 95% normal-approximation confidence interval.

        Returns
        -------
        tuple[float, float]
            ``(lower, upper)`` bounds for the price estimate.
        """
        mean: float = self.price()
        half_width: float = 1.96 * self.std_error()
        return (mean - half_width, mean + half_width)

    def price_both(self) -> dict[str, float]:
        """Price the call and put using the same random draws.

        Reuses one set of simulated terminal prices to price both sides,
        which makes the comparison tighter (shared randomness cancels
        noise in the call-put spread).

        Returns
        -------
        dict[str, float]
            Mapping with keys ``"call"`` and ``"put"``.
        """
        S_T = self._simulate_terminal_prices()
        discount: float = float(np.exp(-self.r * self.T))
        call_payoffs: np.ndarray = np.maximum(S_T - self.K, 0.0)
        put_payoffs: np.ndarray = np.maximum(self.K - S_T, 0.0)
        return {
            "call": float(discount * np.mean(call_payoffs)),
            "put": float(discount * np.mean(put_payoffs)),
        }

    def simulate_paths(self) -> np.ndarray:
        """Return the full simulated price paths.

        Returns
        -------
        numpy.ndarray
            Array of shape ``(n_eff, n_steps + 1)`` where the first
            column is the initial spot ``S`` and the last column is the
            terminal price ``S_T``. ``n_eff = n_paths`` if antithetic is
            ``False``, else ``2 * n_paths``.
        """
        dt: float = self.T / self.n_steps
        drift: float = (self.r - 0.5 * self.sigma ** 2) * dt
        diffusion: float = self.sigma * np.sqrt(dt)

        Z = self._rng.standard_normal(size=(self.n_paths, self.n_steps))
        if self.antithetic:
            Z = np.concatenate([Z, -Z], axis=0)

        log_increments = drift + diffusion * Z
        log_S = np.log(self.S) + np.cumsum(log_increments, axis=1)

        # Prepend log(S) as the t=0 column so the output has shape
        # (n_eff, n_steps + 1).
        paths = np.empty((log_S.shape[0], self.n_steps + 1), dtype=np.float64)
        paths[:, 0] = np.log(self.S)
        paths[:, 1:] = log_S
        return np.exp(paths)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @property
    def _n_eff(self) -> int:
        """Effective number of paths after antithetic pairing."""
        return 2 * self.n_paths if self.antithetic else self.n_paths

    def _simulate_terminal_prices(self) -> np.ndarray:
        """Return the terminal prices ``S_T`` for all paths.

        This is the only function that touches the RNG; ``price()`` and
        ``price_both()`` both call it so they share the same draws when
        invoked in the same :class:`MonteCarloPricer` instance.
        """
        dt: float = self.T / self.n_steps
        drift: float = (self.r - 0.5 * self.sigma ** 2) * dt
        diffusion: float = self.sigma * np.sqrt(dt)

        # ONE NumPy call generates all the random normals.
        Z = self._rng.standard_normal(size=(self.n_paths, self.n_steps))
        if self.antithetic:
            Z = np.concatenate([Z, -Z], axis=0)

        log_increments = drift + diffusion * Z
        # Sum across time steps (axis=1) — vectorized, no Python loop.
        log_S_T = np.log(self.S) + np.sum(log_increments, axis=1)
        return np.exp(log_S_T)

    def _discounted_payoffs(self) -> np.ndarray:
        """Compute discounted payoffs for all paths."""
        S_T = self._simulate_terminal_prices()
        if self.option_type == "call":
            payoff: np.ndarray = np.maximum(S_T - self.K, 0.0)
        else:
            payoff = np.maximum(self.K - S_T, 0.0)
        discount: float = float(np.exp(-self.r * self.T))
        return discount * payoff

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
        n_paths: int,
        n_steps: int,
        option_type: str,
    ) -> None:
        if S <= 0:
            raise ValueError(f"Spot price S must be positive, got {S}.")
        if K <= 0:
            raise ValueError(f"Strike price K must be positive, got {K}.")
        if T <= 0:
            raise ValueError(f"Time to maturity T must be positive, got {T}.")
        if sigma <= 0:
            raise ValueError(f"Volatility sigma must be positive, got {sigma}.")
        if n_paths <= 0:
            raise ValueError(f"n_paths must be positive, got {n_paths}.")
        if n_steps <= 0:
            raise ValueError(f"n_steps must be positive, got {n_steps}.")
        if option_type not in ("call", "put"):
            raise ValueError(
                f"option_type must be 'call' or 'put', got {option_type!r}."
            )

    def __repr__(self) -> str:
        return (
            f"MonteCarloPricer(S={self.S}, K={self.K}, T={self.T}, "
            f"r={self.r}, sigma={self.sigma}, n_paths={self.n_paths}, "
            f"n_steps={self.n_steps}, option_type={self.option_type!r}, "
            f"seed={self.seed}, antithetic={self.antithetic})"
        )
