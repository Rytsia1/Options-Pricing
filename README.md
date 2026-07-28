# Options Pricing Engine

A Python-based quantitative finance repository designed to model, analyze, and calculate financial option prices. This project provides analytical and numerical methods to value derivatives, making it a reliable tool for financial modeling and quantitative analysis.

## 🚀 Features

* **Black-Scholes Model (`src/black_scholes.py`)**: Implements the standard analytical formula for pricing European-style options.
* **Monte Carlo Simulation (`src/monte_carlo.py`)**: Provides a numerical method for options pricing, capable of handling complex or path-dependent derivatives.
* **Market Data Management (`src/market_data.py`)**: Dedicated modules to process and manage the market data variables required for accurate calculations.
* **Robust Testing (`tests/`)**: Fully covered by unit tests using the `pytest` framework to ensure mathematical accuracy and code reliability.

## 📂 Project Structure

* `main.py`: The main entry point for the application.
* `src/`: Contains the core mathematical models and data processing scripts.
* `tests/`: Contains isolated unit tests for all core functionalities (`test_bsm.py`, `test_market_data.py`, `test_monte_carlo.py`).
* `requirements.txt`: Lists all the necessary Python dependencies to run the project.

## 🛠️ Technologies Used

* **Language**: Python, C++
* **Testing Framework**: pytest (v9.1.1)
* **Web Framework**: FastAPI + Uvicorn
* **Containerization**: Docker, Docker Compose

## 🐳 Running with Docker

The project ships with a `Dockerfile` and a `docker-compose.yml` so the
whole engine — **including the C++ `quant_engine_cpp` extension** — can
be built and run with a single command, without installing MSVC, CMake,
or any C++ toolchain on the host.

### Prerequisites

* [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Windows / macOS), or
  Docker Engine + the `docker compose` plugin on Linux.

That's it. Everything else (Python 3.12, `build-essential`, `cmake`,
`pybind11`, FastAPI, Uvicorn, NumPy, yfinance, …) is installed *inside*
the image during the build step, and the C++ Monte-Carlo engine is
compiled at the same time.

### Build & run

From the project root:

```bash
# Modern Docker Compose v2 (ships with Docker Desktop / docker-ce-cli)
docker compose up --build

# Older Docker Compose v1 (still supported by the same docker-compose.yml)
docker-compose up --build
```

The first build takes ~30–60s (mostly the C++ compile). Subsequent
builds are cached and only re-run the steps that actually changed —
editing only `bsm_engine.cpp` will typically re-trigger just the
`cmake --build` step.

Once the container prints something like

```
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

the API is live on `http://localhost:8000`.

### Quick smoke test

```bash
# Health check — should report engine: "C++" because the extension
# was compiled inside the image.
curl http://localhost:8000/

# Price a 3-month ATM call on Apple (defaults to a ~5% risk-free rate).
curl -X POST http://localhost:8000/api/v1/price \
     -H "Content-Type: application/json" \
     -d '{"ticker":"AAPL","strike_price":190.0,"time_to_maturity":0.25}'
```

Interactive Swagger UI is also available at
<http://localhost:8000/docs>.

### Useful commands

```bash
# Run in the background (detached mode)
docker compose up --build -d

# Tail the API logs
docker compose logs -f api

# Stop the service
docker compose down

# Force a clean rebuild of the C++ extension after editing bsm_engine.cpp
docker compose build --no-cache
```

### Rebuilding after editing the C++ source

The compiled `quant_engine_cpp*.so` lives **inside** the image, not on a
bind mount, so any change to `cpp_core/bsm_engine.cpp` (or to
`cpp_core/CMakeLists.txt`) requires rebuilding the image:

```bash
docker compose build         # incremental — only rebuilds the cmake step
# or, if you want a fully clean rebuild:
docker compose build --no-cache
docker compose up
```

### Image layout (for reference)

| Path inside the image          | Purpose                                  |
| ------------------------------ | ---------------------------------------- |
| `/app`                         | `WORKDIR`; project root                  |
| `/app/src/api.py`              | FastAPI application entry point          |
| `/app/cpp_core/bsm_engine.cpp` | C++17 source for the Monte-Carlo engine  |
| `/app/cpp_core/quant_engine_cpp*.so` | Compiled pybind11 module (built during image build) |
| `/app/requirements.txt`        | Python dependencies installed via `pip`   |

If you'd rather not use Docker, the host-side build instructions for
Windows + MSVC are in [`cpp_core/build_instructions.md`](cpp_core/build_instructions.md).
