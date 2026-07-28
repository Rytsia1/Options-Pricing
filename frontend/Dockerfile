# =============================================================================
#  Options Pricing Engine — Streamlit dashboard
#
#  Lightweight image: no C++ toolchain, no pybind11, no FastAPI. The
#  dashboard only talks to the FastAPI backend over HTTP and fetches
#  historical prices from Yahoo Finance directly.
#
#  Build context: project root (.) — so all COPY paths below are
#  prefixed with `frontend/`. The compose file sets the same thing
#  via `build: { context: ., dockerfile: frontend/Dockerfile }`.
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

# 1) Copy the frontend's OWN requirements.txt (which pins streamlit,
#    requests, yfinance, pandas). The previous Dockerfile accidentally
#    picked up the *root* requirements.txt (the backend's), which does
#    not contain streamlit — that's why the container crashed with
#    `exec: "streamlit": executable file not found in $PATH`.
COPY frontend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 2) Belt-and-suspenders: also install the four runtime dependencies
#    explicitly with their bare names. If the COPY above ever fails
#    silently, this RUN still guarantees streamlit is on $PATH.
RUN pip install --no-cache-dir streamlit requests yfinance pandas

# ----- Application source ----------------------------------------------------
# Copy the entire `frontend/` directory (dashboard.py + the requirements
# file we already used) into /app. Using an explicit `frontend/` prefix
# makes the Dockerfile robust to the build context being set elsewhere.
COPY frontend/ ./

# Streamlit's default port.
EXPOSE 8501

# Run Streamlit via `python -m streamlit …` so we don't depend on the
# streamlit console script being on $PATH. This is the official
# Streamlit-in-Docker recommendation and bypasses the exact "streamlit:
# executable file not found" error you saw.
#
# CORS / XSRF: when the browser reaches Streamlit through a Docker
# port-forward (or behind a reverse proxy), the same-origin check and
# the X-Xsrftoken handshake on the WebSocket upgrade can fail with
# HTTP 400. We disable both for this dev/demo setup. For a real
# production deployment, set these to `true` and configure a proper
# origin allowlist / CSRF token strategy.
#
# Tip: set `ENV STREAMLIT_SERVER_HEADLESS=true` (or add
# `--server.headless=true` to the CMD) to suppress the
# "would you like Streamlit to open your browser" prompt at startup.
CMD ["python", "-m", "streamlit", "run", "dashboard.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false"]
