"""Entry point for the Options Pricing Engine.

The script supports two modes:

1. **Demo mode** (no arguments) — runs the original static BSM + Monte
   Carlo demo on a hard-coded set of textbook inputs.
2. **Live mode** (``--ticker AAPL`` or interactive prompt) — fetches the
   spot price and historical volatility for a real ticker via
   :mod:`src.market_data`, then prices a 1-month At-The-Money European
   call with the analytical :class:`EuropeanOption`.

Usage examples
--------------

Run the static demo::

    python main.py

Price a 1-month ATM call on Apple with the default 5% risk-free rate::

    python main.py --ticker AAPL

Override the risk-free rate and maturity::

    python main.py --ticker MSFT --risk-free-rate 0.045 --maturity-years 0.25
"""

from __future__ import annotations

import argparse
import sys

from src.black_scholes import EuropeanOption
from src.market_data import get_market_inputs
from src.monte_carlo import MonteCarloPricer


# ---------------------------------------------------------------------- #
# Static demo (Phase 1-3 demo data)
# ---------------------------------------------------------------------- #
S: float = 100.0
K: float = 100.0
T: float = 1.0
R: float = 0.05
SIGMA: float = 0.20

MC_PATHS: int = 100_000
MC_STEPS: int = 1
MC_SEED: int = 2026
MC_ANTITHETIC: bool = True


def price_option_analytical(option_type: str) -> EuropeanOption:
    """Build the analytical :class:`EuropeanOption` for the static demo."""
    return EuropeanOption(S=S, K=K, T=T, r=R, sigma=SIGMA, option_type=option_type)  # type: ignore[arg-type]


def build_mc_pricer() -> MonteCarloPricer:
    """Build a single MC pricer that will price both call and put."""
    return MonteCarloPricer(
        S=S, K=K, T=T, r=R, sigma=SIGMA,
        n_paths=MC_PATHS, n_steps=MC_STEPS,
        seed=MC_SEED, antithetic=MC_ANTITHETIC,
    )


def print_greeks(option: EuropeanOption) -> None:
    """Pretty-print the option's five Greeks as a small table."""
    g = option.greeks()
    print(f"  Delta : {g['delta']:>10.4f}")
    print(f"  Gamma : {g['gamma']:>10.4f}")
    print(f"  Vega  : {g['vega']:>10.4f}   (per 1.00 = 100% change in sigma)")
    print(f"  Theta : {g['theta']:>10.4f}   (per calendar year)")
    print(f"  Rho   : {g['rho']:>10.4f}   (per 1.00 = 100% change in r)")


def fmt_mc(price: float, std_err: float) -> str:
    """Format a Monte Carlo estimate with its 95% confidence interval."""
    half = 1.96 * std_err
    return f"{price:>8.4f}  (SE={std_err:.4f}, 95% CI=[{price - half:.4f}, {price + half:.4f}])"


def run_static_demo() -> None:
    """Run the original Phase 1-3 BSM + MC comparison on textbook inputs."""
    call_analytical = price_option_analytical("call")
    put_analytical = price_option_analytical("put")
    call_bsm: float = call_analytical.price()
    put_bsm: float = put_analytical.price()

    mc = build_mc_pricer()
    mc_prices = mc.price_both()
    call_mc: float = mc_prices["call"]
    put_mc: float = mc_prices["put"]
    call_mc_se: float = mc.std_error()
    put_mc_se: float = mc.std_error()

    print("Black-Scholes-Merton vs. Monte Carlo")
    print("=" * 60)
    print(
        f"Inputs : S={S}, K={K}, T={T}, r={R}, sigma={SIGMA}\n"
        f"  MC   : {MC_PATHS:,} paths, {MC_STEPS} step(s), "
        f"seed={MC_SEED}, antithetic={MC_ANTITHETIC}"
    )
    print()
    print("Prices")
    print("-" * 60)
    print(f"  BSM (analytical)  Call = {call_bsm:>8.4f}    Put = {put_bsm:>8.4f}")
    print(f"  MC   (estimated)  Call = {fmt_mc(call_mc, call_mc_se)}")
    print(f"                     Put  = {fmt_mc(put_mc,  put_mc_se)}")
    print()
    rel_call = (call_mc - call_bsm) / call_bsm * 100.0
    rel_put = (put_mc - put_bsm) / put_bsm * 100.0
    print(f"  MC vs. BSM error  Call = {rel_call:+7.3f}%    Put = {rel_put:+7.3f}%")

    print()
    print("Call Greeks (BSM analytical)")
    print("-" * 60)
    print_greeks(call_analytical)
    print()
    print("Put Greeks (BSM analytical)")
    print("-" * 60)
    print_greeks(put_analytical)


# ---------------------------------------------------------------------- #
# Live mode — fetch real market data and price a 1-month ATM call
# ---------------------------------------------------------------------- #
def _round_strike(spot: float) -> float:
    """Round the spot to a sensible ATM strike (2-decimal precision)."""
    return float(round(spot, 2))


def run_live_mode(
    ticker: str,
    risk_free_rate: float,
    maturity_years: float,
) -> None:
    """Fetch real market data and price a 1-month ATM call."""
    print(f"Fetching market data for {ticker!r}...")
    inputs = get_market_inputs(ticker)
    spot: float = inputs["S"]
    sigma: float = inputs["sigma"]
    strike: float = _round_strike(spot)

    print()
    print(f"  Spot price (S)     : {spot:>10.4f}")
    print(f"  Strike (K, ATM)    : {strike:>10.4f}")
    print(f"  Ann. vol  (sigma)  : {sigma:>10.4%}")
    print(f"  Risk-free (r)      : {risk_free_rate:>10.4%}")
    print(f"  Maturity (T, yrs)  : {maturity_years:>10.4f}")

    option = EuropeanOption(
        S=spot,
        K=strike,
        T=maturity_years,
        r=risk_free_rate,
        sigma=sigma,
        option_type="call",
    )

    print()
    print("European Call (BSM analytical)")
    print("=" * 60)
    print(f"  Theoretical price  : {option.price():>10.4f}")
    g = option.greeks()
    print(f"  Delta              : {g['delta']:>10.4f}")
    print(f"  Gamma              : {g['gamma']:>10.4f}")
    print(f"  Vega   (per 100% σ): {g['vega']:>10.4f}")
    print(f"  Theta  (per year)  : {g['theta']:>10.4f}")
    print(f"  Rho    (per 100% r): {g['rho']:>10.4f}")


# ---------------------------------------------------------------------- #
# CLI plumbing
# ---------------------------------------------------------------------- #
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="options-pricing",
        description=(
            "Options Pricing Engine demo. "
            "Run with no arguments for the static BSM+MC demo, "
            "or pass --ticker to fetch live market data."
        ),
    )
    parser.add_argument(
        "--ticker",
        type=str,
        default=None,
        help="Stock ticker symbol (e.g. AAPL). If omitted, prompts interactively.",
    )
    parser.add_argument(
        "--risk-free-rate",
        type=float,
        default=0.05,
        help="Continuously-compounded risk-free rate (default: 0.05).",
    )
    parser.add_argument(
        "--maturity-years",
        type=float,
        default=1.0 / 12.0,
        help="Time to maturity in years (default: 1/12 = ~1 month).",
    )
    parser.add_argument(
        "--no-static-demo",
        action="store_true",
        help="Skip the static BSM+MC demo when also running live mode.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    if args.ticker is None and not sys.stdin.isatty():
        # Non-interactive (e.g. CI) and no --ticker → static demo only.
        run_static_demo()
        return

    if args.ticker is None:
        try:
            args.ticker = input("Enter ticker symbol (e.g. AAPL): ").strip().upper()
        except EOFError:
            args.ticker = ""

    if not args.ticker:
        print("No ticker provided — running the static demo instead.")
        run_static_demo()
        return

    if not args.no_static_demo and sys.stdout.isatty():
        # In an interactive terminal, run the static demo first for context.
        run_static_demo()
        print()
        print("#" * 60)
        print()

    run_live_mode(
        ticker=args.ticker,
        risk_free_rate=args.risk_free_rate,
        maturity_years=args.maturity_years,
    )


if __name__ == "__main__":
    main()
