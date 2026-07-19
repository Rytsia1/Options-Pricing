"""Entry point for the Options Pricing Engine.

A small demo script that prices a European call and put using the
:class:`EuropeanOption` Black-Scholes-Merton implementation with
standard textbook inputs:

    S    = 100   (spot price)
    K    = 100   (strike price)
    T    = 1     (time to maturity in years)
    r    = 0.05  (risk-free rate, continuous)
    sigma= 0.20  (volatility)

Run it with::

    python main.py
"""

from __future__ import annotations

from src.black_scholes import EuropeanOption


def price_option(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
    option_type: str,
) -> float:
    """Build a :class:`EuropeanOption` and return its theoretical price."""
    return EuropeanOption(
        S=S,
        K=K,
        T=T,
        r=r,
        sigma=sigma,
        option_type=option_type,  # type: ignore[arg-type]
    ).price()


def main() -> None:
    # --- Dummy market data ---------------------------------------------------
    S: float = 100.0
    K: float = 100.0
    T: float = 1.0
    r: float = 0.05
    sigma: float = 0.20

    # --- Price both option sides --------------------------------------------
    call_price: float = price_option(S, K, T, r, sigma, "call")
    put_price: float = price_option(S, K, T, r, sigma, "put")

    # --- Pretty print results ----------------------------------------------
    print("Black-Scholes-Merton European Option Pricing")
    print("-" * 45)
    print(f"Inputs   : S={S}, K={K}, T={T}, r={r}, sigma={sigma}")
    print(f"Call Price: {call_price:>8.4f}")
    print(f"Put  Price: {put_price:>8.4f}")


if __name__ == "__main__":
    main()
