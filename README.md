# ⚡ High-Performance Options Pricing Engine

[![CI](https://github.com/<YOUR_USERNAME>/Options-Pricing/actions/workflows/ci.yml/badge.svg)](https://github.com/<YOUR_USERNAME>/Options-Pricing/actions/workflows/ci.yml)

A **production-grade, SaaS-ready microservices platform** for pricing European options — combining a multithreaded **C++17 Monte Carlo engine** (via pybind11) with a **FastAPI** backend, API-key authentication, per-subscription rate limiting, and an interactive **Streamlit** dashboard.

Built as a portfolio-quality showcase at the intersection of **quantitative finance** and **modern software engineering**.

---

## 🏗️ Architecture

```
┌─────────────────────┐       HTTP / JSON        ┌──────────────────────────────┐
│                     │  ◄──────────────────────► │                              │
│   Streamlit UI      │     POST /api/v1/price    │   FastAPI Backend            │
│   (Port 8501)       │     X-API-Key header      │   (Port 8000)               │
│                     │                           │                              │
│  • Option inputs    │                           │  • Auth & API Key Mgmt      │
│  • Price display    │                           │  • Rate Limiting (429)      │
│  • C++ vs Py timing │                           │  • Usage Logging            │
│  • Historical chart │                           │  • Market Data (yfinance)   │
└─────────────────────┘                           └──────────┬───────────────────┘
                                                             │
                                                  ┌──────────▼───────────────────┐
                                                  │                              │
                                                  │   C++17 Monte Carlo Engine   │
                                                  │   (pybind11 extension)       │
                                                  │                              │
                                                  │  • Multithreaded simulation  │
                                                  │  • Bypasses Python's GIL    │
                                                  │  • Antithetic variates      │
                                                  └──────────┬───────────────────┘
                                                             │
                                                  ┌──────────▼───────────────────┐
                                                  │   SQLite / PostgreSQL        │
                                                  │   (SQLAlchemy 2.0 ORM)       │
                                                  │                              │
                                                  │  • Users & Subscriptions    │
                                                  │  • API Keys (bcrypt-hashed) │
                                                  │  • Usage Logs (billing)     │
                                                  └─────────────────────────────┘
```

| Layer            | Technology                     | Responsibility                                                  |
| ---------------- | ------------------------------ | --------------------------------------------------------------- |
| **Frontend**     | Streamlit                      | Interactive UI, real-time pricing, historical charts             |
| **Backend**      | FastAPI                        | REST API, authentication, rate limiting, usage logging           |
| **Core Engine**  | C++17 + pybind11               | Multithreaded Monte Carlo — bypasses Python's GIL               |
| **Database**     | SQLite / PostgreSQL (SQLAlchemy) | API key management, user subscriptions, request metering       |
| **CI/CD**        | GitHub Actions                 | Automated build (C++ + Python), lint, and test on every push    |

---

## ✨ Key Features

### Quantitative Finance
- **Black-Scholes Analytical Pricing** — closed-form European call & put with full Greeks (Δ, Γ, ν, Θ, ρ)
- **Monte Carlo Numerical Pricing** — configurable path count (10K–1M), antithetic variates for variance reduction
- **C++17 Engine** — multithreaded simulation compiled as a Python extension via pybind11, delivering significant speedups over pure Python
- **Put-Call Parity Validation** — automatic sanity check on every pricing run
- **Live Market Data** — spot prices and historical volatility fetched in real-time via yfinance

### SaaS Platform
- **User Registration & Auth** — bcrypt-hashed passwords, secure API key issuance
- **API Key Verification** — prefix-based lookup + bcrypt verification on every request
- **Per-Subscription Rate Limiting** — metered API usage with configurable request quotas (HTTP 429 on exhaustion)
- **Usage Logging** — every API call logged with endpoint, execution time, and timestamp for billing & analytics
- **Tiered Subscriptions** — FREE tier (100 requests) with extensible tier model

---

## 📊 Performance Benchmark

> Monte Carlo pricing of a European Call — 100,000 paths, antithetic variates enabled.

| Engine               | Execution Time | Speedup |
| -------------------- | -------------- | ------- |
| **C++ (multithreaded)** | ~X ms       | **~N×** |
| Python (NumPy)       | ~Y ms          | 1×      |

*Run the Streamlit dashboard to see a live head-to-head comparison on your hardware.  
Both engines use identical seeds and path counts for a fair comparison.*

---

## 🚀 Quick Start (Docker)

The entire stack (backend + frontend + C++ compilation) runs with a single command:

```bash
git clone https://github.com/<YOUR_USERNAME>/Options-Pricing.git
cd Options-Pricing
docker compose up --build
```

Once the containers are running:

### 1. Generate an API Key

Open the **FastAPI Swagger UI** at [`http://localhost:8000/docs`](http://localhost:8000/docs).

```
1. POST /auth/register      → Create a user (email + password)
2. POST /auth/generate-key  → Get your raw API key (shown only once!)
```

Copy the `raw_key` from the response — you'll need it for the dashboard.

### 2. Open the Dashboard

Navigate to [`http://localhost:8501`](http://localhost:8501).

```
1. Paste your API Key in the sidebar (🔑 Authentication section)
2. Configure your option parameters (ticker, strike, maturity, etc.)
3. Click "🚀 Price Option"
```

The dashboard will display call/put prices, execution-time comparison (C++ vs Python),
a put-call parity check, and a 1-year historical price chart.

### 3. Use the API Directly

```bash
curl -X POST http://localhost:8000/api/v1/price \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"ticker": "AAPL", "strike_price": 190, "time_to_maturity": 0.25}'
```

---

## 🧪 Testing & CI/CD

The project includes a comprehensive **pytest** suite covering:

- **Black-Scholes** — analytical prices and Greeks against textbook values
- **Monte Carlo** — convergence, variance reduction, put-call parity
- **C++ Engine** — pybind11 extension correctness and consistency with the Python engine
- **API Auth** — key verification, revocation, rate-limit exhaustion (429), usage logging

### Run Tests Locally

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

### CI/CD Pipeline

Every push and pull request to `main` triggers the **GitHub Actions** workflow (`.github/workflows/ci.yml`):

1. Sets up Python 3.12 on `ubuntu-latest`
2. Installs system C++ toolchain (`cmake`, `build-essential`, `python3-dev`)
3. Installs Python dependencies
4. Compiles the C++ Monte Carlo engine
5. Runs the full test suite

---

## 📁 Project Structure

```
Options-Pricing/
├── .github/workflows/ci.yml   # GitHub Actions CI pipeline
├── cpp_core/
│   ├── CMakeLists.txt          # CMake build for the pybind11 extension
│   └── bsm_engine.cpp         # C++17 multithreaded Monte Carlo engine
├── frontend/
│   ├── Dockerfile              # Streamlit container image
│   └── dashboard.py           # Interactive pricing dashboard
├── src/
│   ├── api/
│   │   ├── __init__.py         # FastAPI app, pricing endpoint
│   │   ├── auth.py             # Registration & API key generation
│   │   └── deps.py             # API key verification dependency
│   ├── core/
│   │   └── security.py         # bcrypt hashing, API key generation
│   ├── database/
│   │   ├── models.py           # SQLAlchemy ORM (User, Subscription, ApiKey, UsageLog)
│   │   └── session.py          # Engine, session factory, get_db dependency
│   ├── schemas/
│   │   └── user.py             # Pydantic request/response schemas
│   ├── black_scholes.py        # Analytical BSM pricing + Greeks
│   ├── monte_carlo.py          # Pure-Python Monte Carlo pricer
│   └── market_data.py          # yfinance market data fetcher
├── tests/                      # Pytest suite (BSM, MC, C++, Auth)
├── Dockerfile                  # Backend container (compiles C++ inside)
├── docker-compose.yml          # Full stack orchestration
├── main.py                     # CLI entry point (demo + live mode)
└── requirements.txt            # Python dependencies
```

---

## 📄 License

This project is intended as a portfolio demonstration. See [LICENSE](LICENSE) for details.
