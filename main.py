"""Entry point for the Options Pricing Engine.

A small demo script that prices a European call and put and prints the
five first- and second-order Greeks using the :class:`EuropeanOption`
Black-Scholes-Merton implementation. Standard textbook inputs:

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


def print_greeks(option: EuropeanOption) -> None:
    """Pretty-print the option's five Greeks as a small table."""
    g = option.greeks()
    print(f"  Delta : {g['delta']:>10.4f}")
    print(f"  Gamma : {g['gamma']:>10.4f}")
    print(f"  Vega  : {g['vega']:>10.4f}   (per 1.00 = 100% change in sigma)")
    print(f"  Theta : {g['theta']:>10.4f}   (per calendar year)")
    print(f"  Rho   : {g['rho']:>10.4f}   (per 1.00 = 100% change in r)")


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

    # --- Build the option objects for Greek printing -------------------------
    call_option = EuropeanOption(S=S, K=K, T=T, r=r, sigma=sigma, option_type="call")
    put_option = EuropeanOption(S=S, K=K, T=T, r=r, sigma=sigma, option_type="put")

    # --- Pretty print results ----------------------------------------------
    print("Black-Scholes-Merton European Option Pricing")
    print("=" * 45)
    print(f"Inputs    : S={S}, K={K}, T={T}, r={r}, sigma={sigma}")
    print(f"Call Price: {call_price:>10.4f}")
    print(f"Put  Price: {put_price:>10.4f}")
    print()
    print("Call Greeks:")
    print_greeks(call_option)
    print()
    print("Put Greeks:")
    print_greeks(put_option)


if __name__ == "__main__":
    main()
