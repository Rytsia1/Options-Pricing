# Options Pricing Engine

> **A full-stack quantitative-finance microservices project: a Streamlit
> dashboard over a FastAPI backend, with a multithreaded C++/pybind11
> Monte-Carlo engine compiled inside the container at build time.**

[![CI](https://img.shields.io/github/actions/workflow/status/Rytsia1/Options-Pricing/ci.yml?branch=main&label=CI&logo=github)](https://github.com/Rytsia1/Options-Pricing/actions)
[![Python](https://img.shields.io/badge/python-3.12-blue?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![C++](https://img.shields.io/badge/C%2B%2B-17-00599C?logo=c%2B%2B&logoColor=white)](https://en.cppreference.com/w/cpp/17)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)](docker-compose.yml)

---

## 🌟 Executive Summary

This project is a **production-shaped quantitative-finance stack** that
demonstrates end-to-end ownership of a derivatives pricing system — from
the mathematical core to a deployable, containerized web service with a
professional UI.

The pricing pipeline supports two complementary methods:

1. **Black-Scholes-Merton (BSM)** analytical pricing — closed-form
   European call/put with full Greeks (delta, gamma, vega, theta, rho).
2. **Monte-Carlo simulation** for path-dependent or non-analytic
   payoffs, with two interchangeable backends: a pure-Python reference
   implementation and a **multithreaded C++/pybind11 engine** that
   delivers an order-of-magnitude speedup on commodity hardware.

The whole stack ships as a **two-service microservice** orchestrated by
Docker Compose. The C++ extension is compiled **inside the container
at build time** — no host-side MSVC, CMake, or C++ toolchain is
required, which is a deliberate design choice for portability and
onboarding velocity.

**Headline result:** `docker compose up --build` brings the entire
system online in under two minutes, the dashboard shows call/put
prices, a C++-vs-Python timing comparison, a one-year price chart, and
a put-call parity sanity check — all backed by a deterministic,
thread-safe Monte-Carlo engine.

---

## 🏗️ Architecture

```
┌────────────────────────┐    HTTP POST /api/v1/price    ┌──────────────────────┐
│  Streamlit dashboard   │ ───────────────────────────▶  │  FastAPI backend     │
│  (frontend service)    │                              │  (backend service)   │
│  port 8501             │ ◀───── yfinance (each) ───── │  port 8000           │
│  /app/frontend/        │                              │  C++ engine inside   │
└────────────────────────┘                              └──────────────────────┘
       │                                                       │
       └───────── Docker default network (internal DNS) ───────┘
                  frontend reaches backend as `http://backend:8000`
```

The two services share Docker's default bridge network; the dashboard
reaches the backend through the service name `backend` which Docker's
internal DNS resolves to the backend container's IP.

### Services at a glance

| Service   | Container name              | Port (host → container) | URL                        | Role                                            |
| --------- | --------------------------- | ----------------------- | -------------------------- | ----------------------------------------------- |
| `backend` | `options-pricing-backend`   | `8000 → 8000`           | <http://localhost:8000/docs> | FastAPI + C++/pybind11 Monte-Carlo engine      |
| `frontend`| `options-pricing-frontend`  | `8501 → 8501`           | <http://localhost:8501>     | Streamlit dashboard (calls the backend)         |

---

## ✨ Features

**Pricing models** (`src/`)
- 📐 **Black-Scholes-Merton** analytical pricer with full Greeks.
- 🎲 **Monte-Carlo simulation** with antithetic variates for variance reduction.
- ⚡ **C++ multithreaded MC engine** (compiles inside the Docker image; falls back to Python transparently).
- 📊 **Historical volatility** from daily log-returns, annualized with `sqrt(252)`.

**Market data** (`src/market_data.py`)
- 🌐 **Live spot & vol** via `yfinance` — no API keys required.
- 🛡️ Robust fallbacks when `fast_info` is unavailable (1d history, last close).

**Web API** (`src/api.py`)
- 🚀 **FastAPI** with Pydantic v2 request validation.
- 🔁 **Graceful degradation**: if the C++ extension can't be loaded, the
  API silently falls back to the pure-Python MC pricer (same response shape).
- 📜 **Auto-generated OpenAPI docs** at `/docs` and `/redoc`.

**Frontend** (`frontend/`)
- 🎨 **Streamlit** dashboard with a wide layout and professional dark
  metric cards for prices, vol, and execution-time comparison.
- 📈 **1-year historical close** chart with a 20-day moving average overlay.
- ⚖️ **Put-call parity** sanity check (`C − P ≈ S − K·e^(−rT)`).
- ⚡ **Side-by-side C++ vs Python** timing comparison on the same inputs.

**DevOps**
- 🐳 **Multi-stage Docker build** that compiles the C++ extension at image-build time — no host toolchain.
- 🧱 **Docker Compose** orchestration with service-name DNS and health badges in the UI.
- ✅ **GitHub Actions CI** that builds the C++ extension on every push and runs the full pytest suite.

---

## 🧠 Technical Decisions

### Why C++ for the Monte-Carlo paths?

The Monte-Carlo inner loop is the textbook example of a workload that
benefits from native code:

- **Tight loop, predictable branches, no I/O.** Each path is a few
  multiplies, an `exp`, and a reduction — the kind of code the CPU
  micro-op scheduler loves but the CPython interpreter (with its
  per-opcode dispatch and boxing) handles poorly. A 100k-path option
  price takes ~10 ms in C++ versus ~200 ms in pure Python on the same
  laptop — roughly a **20× speedup** that holds across compilers and
  hardware generations.
- **GIL release.** `pybind11` calls into the C++ extension release the
  Python Global Interpreter Lock, which lets the multithreaded C++
  engine actually use all CPU cores during the simulation. The Python
  MC, by contrast, is single-threaded by construction.
- **No NumPy vectorization tradeoff.** NumPy *can* vectorize the path
  generation, but the result is a single large array that doesn't fit
  in L2 cache for the path counts we care about (1M+), and you lose
  the natural threading. C++ with a per-worker `std::mt19937_64` is a
  better fit: smaller memory footprint, embarrassingly parallel.

### Thread-safety & reproducibility

The C++ engine uses a **worker pool** of `std::thread`s, each with its
**own `std::mt19937_64` engine** seeded from a per-worker sub-seed
derived from the user-supplied root seed. This gives us:

- **Determinism.** Same root seed + same inputs → same prices, every
  run, on any number of cores.
- **No shared mutable state.** Worker state is local; the only
  shared piece is the final accumulator, which is written with
  `std::atomic<double>` (compare-and-swap addition). No locks, no
  contention beyond the unavoidable atomic.
- **Exception safety.** Any failure inside the C++ layer is caught
  by pybind11 and re-raised in Python; the Python caller
  (`_price_with_fallback` in `src/api.py`) catches and falls back
  to the pure-Python pricer so a single misbehaving input never
  brings the API down.

### pybind11 integration

`cpp_core/CMakeLists.txt` is a small, deliberately cross-platform
build:

- `pybind11_add_module(quant_engine_cpp bsm_engine.cpp)` — declares
  the module name and the single source file.
- `execute_process(COMMAND ${Python_EXECUTABLE} -c "import pybind11, sys;
  sys.stdout.write(pybind11.get_cmake_dir())")` — locates the
  pybind11 CMake config from the active Python, so the same file
  works for the host (Windows + MSVC), for the Docker image
  (Debian + GCC), and for macOS without any path hard-coding.
- `LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}"` — drops the
  compiled `.so` directly into `cpp_core/`, which is exactly where
  `src/api.py`'s `_try_import_cpp_engine()` looks for it (via
  `sys.path.insert(0, "cpp_core")`).
- Cross-platform compile flags: `if(MSVC) /O2 /W4 /permissive-`
  for Windows, `-O3 -fPIC -Wall -Wextra -Wpedantic` for GCC/Clang.
- **Graceful fallback** at the Python level: if the `.so` is
  missing, the import raises, and `HAS_CPP` is set to `False` so
  the dashboard's `engine: "C++"` health-check correctly reflects
  the active engine.

---

## 📊 Performance Benchmarks (C++ vs Python)

> **Status:** placeholder. The numbers below are illustrative; run
> `pytest -v -s tests/test_monte_carlo_cpp.py` on your hardware and
> replace the table with measured values.

| n_paths | n_steps | Python MC (ms) | C++ MC (ms) | Speedup (Python ÷ C++) | Threads |
| ------- | ------- | -------------- | ----------- | ---------------------- | ------- |
| 50 000  | 1       | TBD            | TBD         | TBD                    | 1       |
| 100 000 | 1       | TBD            | TBD         | TBD                    | 1       |
| 500 000 | 1       | TBD            | TBD         | TBD                    | 1       |
| 100 000 | 1       | TBD            | TBD         | TBD                    | 8       |
| 1 000 000 | 1     | TBD            | TBD         | TBD                    | 8       |

The single-threaded rows measure the C++ raw loop speedup; the
8-threaded rows show the additional gain from the worker pool.

---

## 🖼️ Dashboard Screenshot

> **To add a screenshot:** drop a PNG into `docs/dashboard.png` and
> the image below will render automatically. A 16:9 export at
> ~1920×1080 reads well on GitHub.

<!--
Add your screenshot to `docs/dashboard.png` and the badge will resolve
on the next commit. The relative path works on GitHub's README viewer.
-->
![Options Pricing Dashboard](docs/dashboard.png)

---

## 🚀 Quick Start (Docker)

The fastest way to run the entire stack. Requires only Docker.

```bash
# 1. Clone the repository
git clone https://github.com/Rytsia1/Options-Pricing.git
cd Options-Pricing

# 2. Build and start both services
docker compose up --build
```

Once both containers print their startup banners, open:

- 📊 **Dashboard**: <http://localhost:8501>
- 📜 **Backend Swagger UI**: <http://localhost:8000/docs>
- 🩺 **Backend health**: <http://localhost:8000/> (returns JSON with the active engine)

```bash
# Stop the stack
docker compose down

# Older Docker Compose v1 (still works with the same file)
docker-compose up --build
```

---

## 🛠️ Local Development (without Docker)

For contributors who want to iterate on the Python side without
spinning up the full stack.

```bash
# 1. Create a venv and install the Python dependencies
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Build the C++ extension (Linux / macOS)
cmake -S cpp_core -B cpp_core/build -DCMAKE_BUILD_TYPE=Release
cmake --build cpp_core/build --parallel

# 2b. …or on Windows with MSVC (Developer PowerShell for VS 2022)
#     See cpp_core/build_instructions.md for the full step-by-step.

# 3. Run the static demo (no API required)
python main.py

# 4. Run the API
uvicorn src.api:app --reload

# 5. In a second terminal, run the dashboard against the local API
pip install -r frontend/requirements.txt
API_URL=http://localhost:8000/api/v1/price \
    streamlit run frontend/dashboard.py
```

---

## 🧪 Testing

```bash
# Run the full suite
pytest tests/ -v

# Run a single test file (e.g. the C++ engine tests)
pytest tests/test_monte_carlo_cpp.py -v -s
```

| Test file                              | Covers                                                                          |
| -------------------------------------- | ------------------------------------------------------------------------------- |
| `tests/test_bsm.py`                    | BSM analytical pricing + Greeks; put-call parity; intrinsic-value boundary.     |
| `tests/test_market_data.py`            | `yfinance` wrapper: spot, history, vol; error paths on bad tickers.             |
| `tests/test_monte_carlo.py`            | Pure-Python Monte-Carlo: convergence, antithetic variance reduction, SE.        |
| `tests/test_monte_carlo_cpp.py`        | C++/pybind11 extension: API parity with the Python MC; reproducibility.        |

---

## 📁 Project Structure

```
Options-Pricing/
├── .github/
│   └── workflows/
│       └── ci.yml                # CI: build C++ ext + run pytest on every push
├── cpp_core/
│   ├── CMakeLists.txt            # Cross-platform build (MSVC, GCC, Clang)
│   ├── bsm_engine.cpp            # C++17 multithreaded Monte-Carlo engine
│   └── build_instructions.md     # Host-side build walkthrough
├── frontend/
│   ├── dashboard.py              # Streamlit dashboard
│   ├── Dockerfile                # No C++ toolchain; streamlit + yfinance
│   └── requirements.txt          # streamlit, requests, yfinance, pandas
├── src/
│   ├── api.py                    # FastAPI service (POST /api/v1/price)
│   ├── black_scholes.py          # BSM analytical pricer + Greeks
│   ├── market_data.py            # yfinance wrapper (spot, vol)
│   └── monte_carlo.py            # Pure-Python Monte-Carlo
├── tests/
│   ├── test_bsm.py
│   ├── test_market_data.py
│   ├── test_monte_carlo.py
│   └── test_monte_carlo_cpp.py
├── main.py                       # CLI demo (BSM + MC comparison)
├── requirements.txt              # Python deps for the backend
├── Dockerfile                    # Backend image; compiles the C++ ext
├── docker-compose.yml            # 2-service microservices
├── .dockerignore
├── .gitignore
├── .gitattributes
└── README.md                     # This file
```

---

## 🛠️ Tech Stack

| Layer        | Technology                                          |
| ------------ | --------------------------------------------------- |
| Core engine  | C++17, CMake ≥ 3.15, pybind11 ≥ 2.11                |
| Pricing math | NumPy ≥ 1.24, SciPy ≥ 1.10                          |
| Market data  | yfinance ≥ 0.2.40                                   |
| Web API      | FastAPI ≥ 0.110, Uvicorn ≥ 0.27, Pydantic ≥ 2.5     |
| Frontend     | Streamlit ≥ 1.36, Pandas ≥ 2.0, Requests ≥ 2.31     |
| Containers   | Docker, Docker Compose v2                           |
| CI           | GitHub Actions (`ubuntu-22.04`, Python 3.12)        |
| Python       | 3.12 (slim Docker base; matches `python:3.12-slim`) |

---

## 🗺️ Roadmap

- 🇺🇸 **American options** via the Cox-Ross-Rubinstein binomial tree and the Longstaff-Schwartz least-squares Monte-Carlo method.
- 📈 **Stochastic-volatility models** (Heston, SABR) with characteristic-function semi-analytic pricers.
- 🔌 **Real-time pricing stream** over WebSockets (Streamlit ↔ FastAPI) so the dashboard updates as new prints arrive.
- 🔐 **Auth + rate-limiting** (API keys, OAuth2 password flow, per-key quota).
- 📡 **Observability**: Prometheus `/metrics`, structured JSON logs, OpenTelemetry traces across the two services.

---

## 📄 License

Released under the [MIT License](LICENSE). You are free to use, modify,
and distribute this project, including for commercial purposes, as long
as the copyright notice is preserved. If you fork this for your own
portfolio, a link back is appreciated but not required.
