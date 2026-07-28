# =============================================================================
#  quant_engine_cpp — C++17 multithreaded Monte Carlo engine for options.
#
#  Builds a Python extension module named `quant_engine_cpp` from
#  `bsm_engine.cpp`, using pybind11 (installed via `pip install pybind11`)
#  and the system C++17 compiler (MSVC, g++, or clang).
#
#  Build (Windows / MSVC, from a Developer PowerShell prompt):
#      cmake -S . -B build -G "Visual Studio 17 2022" -A x64
#      cmake --build build --config Release --parallel
#
#  Build (Linux / macOS):
#      cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
#      cmake --build build --parallel
#
#  The compiled extension is placed at the project root of this directory
#  (`cpp_core/quant_engine_cpp.<abi-tag>.pyd` on Windows or `.so` on Linux)
#  so Python can `import quant_engine_cpp` directly.
# =============================================================================

cmake_minimum_required(VERSION 3.15)
project(quant_engine_cpp LANGUAGES CXX)

# --- C++17 + PIC ------------------------------------------------------------
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

# On Windows (MSVC), use the Release build by default; on multi-config
# generators the user can still select Debug via `--config Debug`.
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

# --- Locate the Python interpreter first ------------------------------------
# NOTE: find_package(Python3 ...) defines Python3_EXECUTABLE (NOT
# Python_EXECUTABLE). Using the wrong variable name here silently expands
# to an empty string, so the pybind11 lookup below would run
# `-c "import pybind11..."` with no interpreter at all and fail (or, worse,
# silently resolve to whatever `cmake` finds on PATH instead of the venv/
# image Python that actually has pybind11 installed).
find_package(Python3 COMPONENTS Interpreter Development REQUIRED)

# --- Locate pybind11 from the active Python environment --------------------
# `pybind11.get_cmake_dir()` is the canonical, cross-platform way to find
# the CMake config files for the pybind11 install in the current venv.
execute_process(
    COMMAND ${Python3_EXECUTABLE} -c "import pybind11, sys; sys.stdout.write(pybind11.get_cmake_dir())"
    OUTPUT_VARIABLE pybind11_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
    RESULT_VARIABLE _pybind11_lookup_result
)
if(NOT _pybind11_lookup_result EQUAL 0 OR pybind11_DIR STREQUAL "")
    message(FATAL_ERROR
        "Could not locate pybind11's CMake config directory using "
        "'${Python3_EXECUTABLE}'. Make sure pybind11 is installed in this "
        "Python environment (pip install pybind11) before configuring.")
endif()
find_package(pybind11 CONFIG REQUIRED)

# --- Threads (pybind11 needs Python dev headers, already required above) ---
find_package(Threads REQUIRED)

# --- Build the extension module --------------------------------------------
pybind11_add_module(quant_engine_cpp
    bsm_engine.cpp
)

# Link against Python (some pybind11 versions don't do this automatically
# when the user-supplied Python is found via find_package rather than via
# the pybind11 toolchain).
target_link_libraries(quant_engine_cpp PRIVATE Python3::Python)
target_link_libraries(quant_engine_cpp PRIVATE Threads::Threads)

# --- Cross-platform compile options -----------------------------------------
# Single source of truth for MSVC vs GCC/Clang flags. Note that
# CMAKE_POSITION_INDEPENDENT_CODE=ON (set above) already covers -fPIC for
# the project, but we list it explicitly here so the GCC branch is
# self-documenting and matches the documented contract.
if(MSVC)
    target_compile_options(quant_engine_cpp PRIVATE /O2 /W4 /permissive-)
else()
    # GCC / Clang — this is the path taken inside the Docker image
    # (g++ on Debian slim) and on macOS.
    target_compile_options(quant_engine_cpp PRIVATE
        -O3
        -fPIC
        -Wall -Wextra -Wpedantic
        -Wno-unused-parameter   # pybind11 boilerplate triggers this benignly
    )
endif()

# Place the compiled module at the project root of cpp_core/ so a
# one-line `sys.path.insert(0, "cpp_core")` in main.py makes
# `import quant_engine_cpp` work.
set_target_properties(quant_engine_cpp PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}"
)
