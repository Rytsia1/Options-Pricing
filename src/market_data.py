"""Real-world market data helpers backed by ``yfinance``.

This module provides a small, typed surface on top of the ``yfinance``
library for fetching spot prices, historical prices, and computing the
annualized historical volatility of a stock.

Conventions
-----------
* **Volatility** is computed from daily log-returns of the closing
  prices and annualized with ``sqrt(trading_days)``. The default
  ``trading_days=252`` matches the standard US equity calendar.
* **Spot** comes from ``Ticker.fast_info.last_price`` (lightweight,
  no historical download). If unavailable (some indices, funds, or
  during a network outage), we fall back to the last close of a
  one-day history pull.
* All public functions return plain Python types (``float``,
  ``pandas.Series``) so the rest of the engine doesn't need to know
  about yfinance.
"""

from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd
import yfinance as yf


DEFAULT_TRADING_DAYS: Final[int] = 252
DEFAULT_HISTORY_PERIOD: Final[str] = "1y"


# ---------------------------------------------------------------------- #
# Public API
# ---------------------------------------------------------------------- #
def fetch_spot(ticker: str) -> float:
    """Return the latest available price for ``ticker``.

    Uses ``Ticker.fast_info.last_price`` (no full history download)
    and falls back to the most recent 1-day close if the fast info
    field is ``None`` (some tickers don't populate it).

    Parameters
    ----------
    ticker : str
        A valid Yahoo Finance ticker symbol (e.g. ``"AAPL"``,
        ``"MSFT"``, ``"^GSPC"``).

    Returns
    -------
    float
        The current spot price.

    Raises
    ------
    ValueError
        If no price can be determined for ``ticker``.
    """
    t = yf.Ticker(ticker)
    fast = getattr(t, "fast_info", None)
    if fast is not None:
        last_price = getattr(fast, "last_price", None)
        if last_price is not None and not (isinstance(last_price, float) and np.isnan(last_price)):
            return float(last_price)

    # Fallback: pull a single day of history and take the last close.
    hist = t.history(period="1d", auto_adjust=False)
    if hist.empty or "Close" not in hist.columns:
        raise ValueError(
            f"Could not determine spot price for ticker {ticker!r}: "
            "fast_info and 1d history both empty."
        )
    return float(hist["Close"].iloc[-1])


def fetch_history(
    ticker: str,
    period: str = DEFAULT_HISTORY_PERIOD,
) -> pd.Series:
    """Download the daily closing-price history for ``ticker``.

    Parameters
    ----------
    ticker : str
        A valid Yahoo Finance ticker symbol.
    period : str
        Any ``yfinance``-compatible period string. Defaults to
        ``"1y"``.

    Returns
    -------
    pandas.Series
        Daily closing prices, indexed by date, sorted oldest → newest.
        The series name is ``"Close"``.
    """
    t = yf.Ticker(ticker)
    hist = t.history(period=period, auto_adjust=True)
    if hist.empty or "Close" not in hist.columns:
        raise ValueError(
            f"No history returned for ticker {ticker!r} "
            f"(period={period!r}). Check the symbol and try again."
        )
    close: pd.Series = hist["Close"].copy()
    close.name = "Close"
    close.index = pd.to_datetime(close.index)
    return close.sort_index()


def historical_volatility(
    prices: pd.Series,
    trading_days: int = DEFAULT_TRADING_DAYS,
) -> float:
    """Compute the annualized historical volatility of a price series.

    The convention is the standard one in quantitative finance::

        sigma = std( log(P_t / P_{t-1}) ) * sqrt(trading_days)

    Parameters
    ----------
    prices : pandas.Series
        A price series (e.g. daily closes) sorted oldest → newest.
    trading_days : int
        Number of trading days used to annualize the volatility.
        Defaults to ``252`` (US equities).

    Returns
    -------
    float
        The annualized volatility as a decimal (e.g. ``0.20`` for 20%).

    Raises
    ------
    ValueError
        If ``prices`` has fewer than two observations or contains
        non-positive values.
    """
    if trading_days <= 0:
        raise ValueError(f"trading_days must be positive, got {trading_days}.")

    clean = prices.dropna()
    if len(clean) < 2:
        raise ValueError(
            "historical_volatility requires at least two observations; "
            f"got {len(clean)}."
        )
    if (clean <= 0).any():
        raise ValueError("historical_volatility requires strictly positive prices.")

    log_returns = np.log(clean / clean.shift(1)).dropna()
    return float(log_returns.std(ddof=1) * np.sqrt(trading_days))


def get_market_inputs(
    ticker: str,
    period: str = DEFAULT_HISTORY_PERIOD,
    trading_days: int = DEFAULT_TRADING_DAYS,
) -> dict[str, float]:
    """Fetch spot and annualized volatility for ``ticker`` in one call.

    Parameters
    ----------
    ticker : str
        A valid Yahoo Finance ticker symbol.
    period : str
        History period passed to :func:`fetch_history`. Defaults to
        ``"1y"``.
    trading_days : int
        Annualization factor for :func:`historical_volatility`.

    Returns
    -------
    dict[str, float]
        Mapping with keys ``"S"`` (current spot) and ``"sigma"``
        (annualized historical volatility).
    """
    history = fetch_history(ticker, period=period)
    return {
        "S": fetch_spot(ticker),
        "sigma": historical_volatility(history, trading_days=trading_days),
    }
