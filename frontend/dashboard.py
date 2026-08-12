"""Streamlit dashboard for the Options Pricing Engine.

A small front-end microservice that:
  1. Collects pricing inputs in a sidebar form (ticker, strike, maturity,
     risk-free rate, Monte-Carlo path count).
  2. POSTs them to the FastAPI backend's ``/api/v1/price`` endpoint and
     renders the returned call / put / vol / spot prices in a grid of
     ``st.metric`` cards.
  3. Requests a *second* pricing run with ``force_engine="python"`` so
     the user can see a real C++ vs Python execution-time comparison.
  4. Fetches one year of daily closing prices for the entered ticker
     directly via ``yfinance`` and plots them with a 20-day moving
     average overlay.
  5. Displays a put-call parity sanity check at the bottom.

The backend URL is read from the ``API_URL`` environment variable and
defaults to ``http://backend:8000/api/v1/price`` so the dashboard works
out-of-the-box when launched via ``docker compose up``.
"""

from __future__ import annotations

import math
import os
from typing import Any

import pandas as pd
import requests
import streamlit as st
import yfinance as yf


# ---------------------------------------------------------------------- #
# Configuration
# ---------------------------------------------------------------------- #
# Default points at the *service name* on the Docker compose network
# (Docker's internal DNS resolves `backend` → the api container).
API_URL: str = os.getenv("API_URL", "http://backend:8000/api/v1/price")
HEALTH_URL: str = os.getenv("API_HEALTH_URL", "http://backend:8000/")


st.set_page_config(
    page_title="Options Pricing Engine",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(ticker: str) -> pd.DataFrame:
    """Download ~1 year of daily closes for *ticker*.

    Wrapped in :func:`st.cache_data` so repeated slider adjustments
    don't hammer Yahoo Finance.

    Raises
    ------
    ValueError
        If yfinance returns no data (bad ticker, network outage, etc.).
    """
    hist = yf.Ticker(ticker).history(period="1y", auto_adjust=True)
    if hist.empty or "Close" not in hist.columns:
        raise ValueError(
            f"No price history returned for ticker {ticker!r}. "
            "Check the symbol and try again."
        )
    return hist


def post_price(
    payload: dict[str, Any],
    api_key: str,
    timeout: float = 30.0,
) -> requests.Response:
    """POST *payload* to the backend and return the raw :class:`Response`.

    The caller is responsible for inspecting ``resp.status_code`` and
    handling 401 / 429 / other errors with the appropriate UI feedback.

    Raises
    ------
    requests.RequestException
        For connection / timeout errors.
    """
    headers = {
        "User-Agent": "options-pricing-dashboard/1.0 (+streamlit)",
        "X-API-Key": api_key,
    }
    return requests.post(API_URL, json=payload, headers=headers, timeout=timeout)


def check_backend() -> bool:
    """Best-effort health check; returns ``True`` if the backend is up."""
    try:
        r = requests.get(HEALTH_URL, timeout=2.0)
        return r.ok
    except requests.RequestException:
        return False


# ---------------------------------------------------------------------- #
# Sidebar — user inputs
# ---------------------------------------------------------------------- #
with st.sidebar:
    st.header("🔑 Authentication")
    api_key = st.text_input(
        "Enter your API Key",
        type="password",
        help="Your API key issued via POST /auth/generate-key.",
    )
    st.divider()
    st.header("⚙️ Pricing Inputs")

    with st.form("pricing_form", clear_on_submit=False):
        ticker = st.text_input(
            "Ticker Symbol",
            value="AAPL",
            max_chars=10,
            help="Yahoo Finance ticker, e.g. AAPL, MSFT, TSLA, ^GSPC.",
        ).strip().upper()

        strike_price = st.number_input(
            "Strike Price (K)",
            min_value=0.01,
            value=190.0,
            step=1.0,
            format="%.2f",
            help="Strike price of the European option.",
        )

        time_to_maturity = st.slider(
            "Time to Maturity (years)",
            min_value=0.01,
            max_value=5.0,
            value=0.25,
            step=0.01,
            help="Time to expiration in years. 0.25 ≈ 3 months.",
        )

        risk_free_rate = st.number_input(
            "Risk-Free Rate (r)",
            min_value=0.0,
            max_value=0.20,
            value=0.05,
            step=0.005,
            format="%.3f",
            help="Continuously-compounded risk-free rate. 0.05 ≈ 5%.",
        )

        n_paths = st.slider(
            "Number of Monte Carlo Paths",
            min_value=10_000,
            max_value=1_000_000,
            value=100_000,
            step=10_000,
            help=(
                "More paths = tighter confidence interval, slower run. "
                "Backend caps this at [10,000, 1,000,000] to prevent abuse."
            ),
        )

        submitted = st.form_submit_button(
            "🚀 Price Option",
            use_container_width=True,
        )

    st.divider()
    backend_ok = check_backend()
    if backend_ok:
        st.success("Backend reachable ✅", icon="🟢")
    else:
        st.warning("Backend not reachable — start it with `docker compose up`.", icon="🟠")

    st.caption(
        f"API URL: `{API_URL}`\n\n"
        "Override with the `API_URL` environment variable if running "
        "the dashboard outside of Docker Compose."
    )


# ---------------------------------------------------------------------- #
# Main panel
# ---------------------------------------------------------------------- #
st.title("📈 Options Pricing Engine")
st.markdown(
    "A microservices demo: a **C++/pybind11** Monte-Carlo engine compiled "
    "inside a FastAPI backend, fronted by this Streamlit dashboard. "
    "Fill in the sidebar and click **Price Option**."
)

if not submitted:
    st.info("👈 Set your inputs in the sidebar and click **Price Option** to begin.")
    st.stop()

# Guard: API key is required before we hit the backend.
if not api_key:
    st.warning("⚠️ Please enter your API Key in the sidebar before pricing.")
    st.stop()


# ---------------------------------------------------------------------- #
# Build request payload
# ---------------------------------------------------------------------- #
# We make *two* calls to the backend:
#   1. `force_engine="auto"`  → uses the C++ engine if available, else Python.
#   2. `force_engine="python"` → forces the pure-Python path so we can
#      show a real C++ vs Python execution-time comparison.
base_payload: dict[str, Any] = {
    "ticker": ticker,
    "strike_price": float(strike_price),
    "time_to_maturity": float(time_to_maturity),
    "risk_free_rate": float(risk_free_rate),
    "n_paths": int(n_paths),
}
payload_cpp = {**base_payload, "force_engine": "auto"}
payload_py = {**base_payload, "force_engine": "python"}


# ---------------------------------------------------------------------- #
# Call the backend (twice — for the C++ vs Python comparison)
# ---------------------------------------------------------------------- #
def _handle_response(resp: requests.Response, label: str) -> dict[str, Any]:
    """Inspect *resp* and return parsed JSON, or stop with an error."""
    if resp.status_code == 200:
        return resp.json()
    if resp.status_code == 401:
        st.error("🔒 Unauthorized: Invalid or revoked API Key.")
        st.stop()
    if resp.status_code == 429:
        st.error(
            "⏳ Rate Limit Exceeded: You have run out of your "
            "monthly compute quota."
        )
        st.stop()
    # Fallback for any other non-200 status.
    st.error(
        f"Backend error on {label} request "
        f"(HTTP {resp.status_code}): {resp.text}"
    )
    st.stop()
    return {}  # unreachable; keeps type-checkers happy


with st.spinner("Pricing on the backend…"):
    try:
        cpp_resp = post_price(payload_cpp, api_key=api_key)
        cpp_result = _handle_response(cpp_resp, "auto-engine")
        py_resp = post_price(payload_py, api_key=api_key)
        py_result = _handle_response(py_resp, "python-forced")
    except requests.RequestException as exc:
        st.error(f"Could not reach the backend at `{API_URL}`.\n\n{exc}")
        st.stop()


# ---------------------------------------------------------------------- #
# Result metrics — top row
# ---------------------------------------------------------------------- #
st.subheader("💰 Option Prices")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Call Price", f"${cpp_result['call_price']:.4f}")
c2.metric("Put Price", f"${cpp_result['put_price']:.4f}")
c3.metric("Volatility (σ)", f"{cpp_result['volatility']:.2%}")
c4.metric("Spot Price (S)", f"${cpp_result['spot_price']:.4f}")


# ---------------------------------------------------------------------- #
# Result metrics — execution-time comparison
# ---------------------------------------------------------------------- #
st.subheader("⚡ Execution-Time Comparison")

cpp_ms: float = float(cpp_result["execution_time_ms"])
py_ms: float = float(py_result["execution_time_ms"])
cpp_engine: str = cpp_result["engine_used"]  # "C++" or "Python"
py_engine: str = py_result["engine_used"]   # always "Python" when forced

speedup: float | None = None
if cpp_engine == "C++" and py_ms > 0:
    speedup = py_ms / cpp_ms

m1, m2, m3 = st.columns(3)
m1.metric(
    f"{cpp_engine} engine",
    f"{cpp_ms:.2f} ms",
    help="Time for the auto/forced-C++ path on the backend.",
)
m2.metric(
    f"{py_engine} engine (forced)",
    f"{py_ms:.2f} ms",
    help="Time for a forced Python-only pricing run on the same inputs.",
)
m3.metric(
    "Speedup (Python ÷ C++)",
    f"{speedup:.2f}×" if speedup is not None else "n/a",
    delta=None,
    help="How many times faster the C++ engine was than pure-Python.",
)

if cpp_engine == "Python":
    st.info(
        "ℹ️ The C++ extension is not loaded on the backend (engine fell "
        "back to Python). Both timings above are pure-Python."
    )


# ---------------------------------------------------------------------- #
# Put-call parity sanity check
# ---------------------------------------------------------------------- #
with st.expander("🔬 Put-Call Parity Check", expanded=True):
    S = float(cpp_result["spot_price"])
    K = float(cpp_result["strike_price"])
    T = float(cpp_result["time_to_maturity"])
    r = float(cpp_result["risk_free_rate"])
    C = float(cpp_result["call_price"])
    P = float(cpp_result["put_price"])

    theoretical_diff = S - K * math.exp(-r * T)
    actual_diff = C - P
    parity_error_pct = (
        abs(actual_diff - theoretical_diff) / S * 100.0 if S > 0 else 0.0
    )

    pc1, pc2, pc3 = st.columns(3)
    pc1.metric("C − P (model)", f"${actual_diff:.4f}")
    pc2.metric("S − K·e^(−rT) (theoretical)", f"${theoretical_diff:.4f}")
    pc3.metric("Parity error", f"{parity_error_pct:.3f}%")

    if parity_error_pct < 1.0:
        st.success(
            f"✅ Put-call parity holds within {parity_error_pct:.3f}% "
            f"of spot — the MC engine is producing consistent prices."
        )
    else:
        st.warning(
            f"⚠️ Parity gap is {parity_error_pct:.3f}% of spot. "
            "This is normal for a Monte-Carlo estimate with finite paths; "
            "increase the path count in the sidebar to tighten it."
        )


# ---------------------------------------------------------------------- #
# Historical price chart
# ---------------------------------------------------------------------- #
st.subheader(f"📉 {ticker} — 1-Year Closing Price History")

try:
    hist = fetch_history(ticker)
    close: pd.Series = hist["Close"].astype(float).copy()
    close.name = "Close"
    ma20: pd.Series = close.rolling(window=20).mean()
    ma20.name = "20-day MA"

    chart_df = pd.concat([close, ma20], axis=1).dropna()
    st.line_chart(chart_df, height=380, use_container_width=True)

    st.caption(
        f"Source: Yahoo Finance · "
        f"{len(close):,} trading days · "
        f"range: {close.index.min().date()} → {close.index.max().date()}"
    )
except ValueError as exc:
    st.error(f"Could not load price history: {exc}")
except Exception as exc:  # pragma: no cover — defensive UI fallback
    st.error(f"Unexpected error while fetching history: {exc}")


# ---------------------------------------------------------------------- #
# Raw response (for debugging / curiosity)
# ---------------------------------------------------------------------- #
with st.expander("🛠️ Raw backend response"):
    st.json({"auto_engine": cpp_result, "python_forced": py_result})

with st.expander("🔍 Outgoing request payload (debug)"):
    st.caption(
        "Exact JSON body POSTed to the backend. If you ever see a "
        "4xx error, this is the first place to look."
    )
    st.json({
        "force_engine='auto'":  payload_cpp,
        "force_engine='python'": payload_py,
    })


# ---------------------------------------------------------------------- #
# Troubleshooting cheatsheet
# ---------------------------------------------------------------------- #
with st.expander("❓ Troubleshooting"):
    st.markdown(
        """
**HTTP 400 from the backend** — the request body parsed successfully
(FastAPI returns 422 for shape errors). A 400 is raised by the
backend when Yahoo Finance can't resolve the ticker (typo, delisted
symbol, index not covered, rate-limited). Try a different ticker
(e.g. `AAPL`, `MSFT`, `^GSPC`).

**HTTP 422 from the backend** — a field is missing or has the wrong
type. Inspect the payload in the expander above and compare it to the
backend's `PricingRequest` model in `src/api.py`.

**Connection error** — the dashboard can't reach `API_URL`. If you're
running outside Docker Compose, set the `API_URL` env var, e.g.
`API_URL=http://localhost:8000/api/v1/price`.

**Streamlit page won't load** — the WebSocket handshake was blocked.
The `frontend/Dockerfile` already disables CORS and XSRF; if you're
running Streamlit outside of Docker, add the same flags to the
`streamlit run` command.
"""
    )
