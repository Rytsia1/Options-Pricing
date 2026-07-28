# =============================================================================
#  Options Pricing Engine — Streamlit dashboard
#
#  Lightweight image: no C++ toolchain, no pybind11, no FastAPI. The
#  dashboard only talks to the FastAPI backend over HTTP and fetches
#  historical prices from Yahoo Finance directly.
# =============================================================================

FROM python:3.12-slim

# Streamlit runs as a long-lived server; unbuffered stdout/stderr so
# `docker compose logs -f frontend` shows the UI reload / rerun output
# in real time.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ----- Python dependencies ---------------------------------------------------
WORKDIR /app

# Copy only the requirements first for layer caching.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# ----- Application source ----------------------------------------------------
COPY . .

# Streamlit's default port.
EXPOSE 8501

# `--server.headless=true` is mandatory inside a container — without it
# Streamlit tries to spawn a browser and prints a usage error.
# `--server.address=0.0.0.0` is what makes the dashboard reachable from
# the host (and from other containers on the Docker network).
CMD ["streamlit", "run", "dashboard.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
