"""FastAPI microservice exposing the Options Pricing Engine over HTTP.

This module wraps the existing quant engine — both the Python
:class:`~src.monte_carlo.MonteCarloPricer` and the optional C++
``quant_engine_cpp`` extension — behind a small REST surface so that
external trading platforms or frontends can request option prices
without having to know about the internal math.

Endpoints
---------
* ``GET  /``            — health-ping that also reports which engine the
                          service is currently configured to use.
* ``POST /api/v1/price`` — price a European call + put for a real
                          ticker using live market data.

Engine selection
----------------
At import time we try to load ``quant_engine_cpp`` from ``cpp_core/``.
If that succeeds the service runs the multithreaded C++ Monte Carlo
engine; on any failure (extension not built, missing MSVC, import
error, etc.) we silently fall back to the pure-Python
:class:`~src.monte_carlo.MonteCarloPricer`. The ``engine_used`` field in
the response tells the caller which path was taken.
"""

from __future__ import annotations

import pathlib
import sys
import time
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.market_data import get_market_inputs
from src.monte_carlo import MonteCarloPricer


# ---------------------------------------------------------------------- #
# Monte-Carlo defaults — keep them in one place so they're easy to tune.
# ---------------------------------------------------------------------- #
MC_N_PATHS: int = 100_000
MC_N_STEPS: int = 1
MC_SEED: int = 2026
MC_ANTITHETIC: bool = True
MC_CPP_THREADS: int = 0  # 0 → let the C++ engine pick (hardware_concurrency)


# ---------------------------------------------------------------------- #
# Optional C++ engine loader (mirrors the logic in main.py / tests).
# ---------------------------------------------------------------------- #
def _try_import_cpp_engine() -> object | None:
    """Try to import the ``quant_engine_cpp`` extension.

    Returns the module on success, or ``None`` if the C++ build is not
    available (no ``cpp_core`` directory, missing MSVC, etc.).
    """
    cpp_dir = pathlib.Path(__file__).resolve().parent.parent / "cpp_core"
    if not cpp_dir.exists():
        return None
    sys.path.insert(0, str(cpp_dir))
    try:
        import quant_engine_cpp  # type: ignore[import-not-found]
        return quant_engine_cpp
    except Exception:
        return None


quant_engine_cpp = _try_import_cpp_engine()
HAS_CPP: bool = quant_engine_cpp is not None


# ---------------------------------------------------------------------- #
# Pydantic models — strict input validation + a clean response shape.
# ---------------------------------------------------------------------- #
class PricingRequest(BaseModel):
    """Input payload for ``POST /api/v1/price``.

    Attributes
    ----------
    ticker : str
        Yahoo Finance ticker symbol (e.g. ``"AAPL"``). Will be uppercased
        and stripped of surrounding whitespace before use.
    strike_price : float
        Strike price ``K`` of the option. Must be strictly positive.
    time_to_maturity : float
        Time to maturity ``T`` in years. Must be strictly positive.
    risk_free_rate : float, optional
        Continuously-compounded risk-free rate. Defaults to ``0.05``
        (≈ 5%).
    """

    ticker: str = Field(min_length=1, max_length=10)
    strike_price: float = Field(gt=0.0, description="Strike price K, must be > 0")
    time_to_maturity: float = Field(gt=0.0, description="Time to maturity T (years), must be > 0")
    risk_free_rate: float = Field(
        default=0.05,
        description="Continuously-compounded risk-free rate (default 0.05)",
    )

    @field_validator("ticker")
    @classmethod
    def _normalize_ticker(cls, v: str) -> str:
        """Trim whitespace and uppercase the ticker."""
        v = v.strip()
        if not v:
            raise ValueError("ticker must not be empty")
        return v.upper()


class PricingResponse(BaseModel):
    """Output payload returned by ``POST /api/v1/price``."""

    ticker: str
    spot_price: float
    volatility: float
    strike_price: float
    time_to_maturity: float
    risk_free_rate: float
    call_price: float
    put_price: float
    execution_time_ms: float
    engine_used: Literal["C++", "Python"]


# ---------------------------------------------------------------------- #
# Pricing core — try C++, fall back to Python.
# ---------------------------------------------------------------------- #
def _price_with_cpp(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
) -> tuple[float, float]:
    """Run the C++ Monte Carlo engine; return ``(call_price, put_price)``.

    Raises whatever the underlying C++ extension raises — the caller
    (``_price_with_fallback``) is responsible for catching it.
    """
    assert quant_engine_cpp is not None  # only called when HAS_CPP is True
    cpp = quant_engine_cpp  # type: ignore[assignment]
    pricer = cpp.MonteCarloPricerCpp(  # type: ignore[attr-defined]
        S, K, T, r, sigma,
        MC_N_PATHS, MC_N_STEPS, "call",
        MC_SEED, MC_ANTITHETIC, MC_CPP_THREADS,
    )
    call_price, put_price = pricer.price_both()
    return float(call_price), float(put_price)


def _price_with_python(
    S: float,
    K: float,
    T: float,
    r: float,
    sigma: float,
) -> tuple[float, float]:
    """Run the pure-Python :class:`MonteCarloPricer`; return ``(call, put)``."""
    pricer = MonteCarloPricer(
        S=S, K=K, T=T, r=r, sigma=sigma,
        n_paths=MC_N_PATHS,
        n_steps=MC_N_STEPS,
        seed=MC_SEED,
        antithetic=MC_ANTITHETIC,
        option_type="call",
    )
    prices = pricer.price_both()
    return float(prices["call"]), float(prices["put"])


def _price_with_fallback(
    S: float, K: float, T: float, r: float, sigma: float,
) -> tuple[float, float, Literal["C++", "Python"]]:
    """Try the C++ engine first, fall back to Python on any error.

    Returns
    -------
    tuple[float, float, Literal["C++", "Python"]]
        ``(call_price, put_price, engine_used)``.
    """
    if HAS_CPP:
        try:
            call, put = _price_with_cpp(S, K, T, r, sigma)
            return call, put, "C++"
        except Exception:
            # Any failure in the C++ path (ImportError, AttributeError,
            # a segfault caught by pybind11, etc.) → fall back to Python.
            pass
    call, put = _price_with_python(S, K, T, r, sigma)
    return call, put, "Python"


# ---------------------------------------------------------------------- #
# FastAPI application
# ---------------------------------------------------------------------- #
app = FastAPI(
    title="Options Pricing Engine",
    description=(
        "REST microservice around the Options Pricing engine. "
        "Prices European calls and puts via Monte Carlo simulation, "
        "preferring the multithreaded C++ engine when available."
    ),
    version="0.1.0",
)


@app.get("/", tags=["health"])
def root() -> dict[str, str]:
    """Health-ping endpoint that reports which engine is active."""
    return {
        "service": "options-pricing",
        "version": app.version,
        "engine": "C++" if HAS_CPP else "Python",
        "status": "ok",
    }


@app.post(
    "/api/v1/price",
    response_model=PricingResponse,
    tags=["pricing"],
    summary="Price a European option for a real ticker",
)
def price_option(payload: PricingRequest) -> PricingResponse:
    """Fetch live market data and run a Monte Carlo pricing.

    Request body
    ------------
    A :class:`PricingRequest` JSON object.

    Returns
    -------
    PricingResponse
        Call and put prices, the inputs actually used (spot, vol, etc.),
        wall-clock execution time, and the engine that ran the simulation.
    """
    # 1. Fetch spot + historical vol from yfinance.
    try:
        market = get_market_inputs(payload.ticker)
    except ValueError as exc:
        # yfinance couldn't resolve the ticker / no data available.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Network or upstream error — surface as a 502 Bad Gateway.
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch market data for {payload.ticker!r}: {exc}",
        ) from exc

    spot: float = float(market["S"])
    sigma: float = float(market["sigma"])

    # 2. Run the engine (C++ if available, else Python fallback).
    t0 = time.perf_counter()
    call_price, put_price, engine_used = _price_with_fallback(
        S=spot,
        K=payload.strike_price,
        T=payload.time_to_maturity,
        r=payload.risk_free_rate,
        sigma=sigma,
    )
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # 3. Shape the response.
    return PricingResponse(
        ticker=payload.ticker,
        spot_price=spot,
        volatility=sigma,
        strike_price=payload.strike_price,
        time_to_maturity=payload.time_to_maturity,
        risk_free_rate=payload.risk_free_rate,
        call_price=call_price,
        put_price=put_price,
        execution_time_ms=elapsed_ms,
        engine_used=engine_used,
    )
