# =============================================================================
#  Options Pricing Engine — production-style image
#
#  Single-stage build on `python:3.12-slim`. We deliberately do NOT use a
#  multi-stage image here: keeping the toolchain in the final image lets us
#  rebuild the C++ extension on demand (e.g. via `docker compose build` after
#  editing `bsm_engine.cpp`) without juggling two Dockerfiles.
#
#  The C++ extension `quant_engine_cpp` is built *inside* this image during
#  the Docker build step, so the resulting image is self-contained — no MSVC,
#  no Visual Studio, no CMake install required on the host.
# =============================================================================

FROM python:3.12-slim

# ----- Runtime niceties ------------------------------------------------------
# - PYTHONDONTWRITEBYTECODE: don't litter the image with .pyc files.
# - PYTHONUNBUFFERED        : stream uvicorn logs straight to the container
#                             stdout (essential for `docker logs`).
# - PIP_NO_CACHE_DIR        : keep the pip layer small.
# - PIP_DISABLE_PIP_VERSION_CHECK : silence noisy upgrade nag during build.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ----- System build tools ----------------------------------------------------
# - `build-essential` ships gcc, g++, and make.
# - `cmake`        is required by cpp_core/CMakeLists.txt.
# - `python3-dev`  pulls in libpython3.12-dev (Python.h headers +
#                   the libpython3.12.so symlink). Without it,
#                   `find_package(Python3 COMPONENTS Development REQUIRED)`
#                   in cpp_core/CMakeLists.txt fails on Debian slim, and
#                   pybind11 cannot locate Python.h. This is the most
#                   common cause of `exit code 1` in the cmake step.
# We install with --no-install-recommends and purge the apt lists in the same
# RUN to keep the layer as small as possible.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# ----- Python dependencies ---------------------------------------------------
WORKDIR /app

# Copy ONLY the requirements file first so this layer (and the heavy pip
# install) is cached as long as requirements.txt doesn't change.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# ----- Application source ----------------------------------------------------
# Copy the rest of the repo. .dockerignore keeps build artifacts, .git, etc.
# out of the build context.
COPY . .

# ----- Build the C++ extension inside the image ------------------------------
# The existing cpp_core/CMakeLists.txt auto-locates pybind11 from the active
# Python (`pybind11.get_cmake_dir()`) and drops the resulting
# `quant_engine_cpp*.so` directly into the `cpp_core/` directory, which is
# exactly where `src/api.py`'s `_try_import_cpp_engine()` looks for it.
# Use Release for an optimized Monte-Carlo hot path.
RUN cmake -S cpp_core -B cpp_core/build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build cpp_core/build --parallel

# ----- Runtime ---------------------------------------------------------------
EXPOSE 8000

# Exec form is required so uvicorn receives SIGTERM/SIGINT directly (so
# `docker stop` shuts the API down gracefully).
CMD ["uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
