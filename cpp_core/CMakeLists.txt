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

# --- Locate pybind11 from the active Python environment --------------------
# `pybind11.get_cmake_dir()` is the canonical, cross-platform way to find
# the CMake config files for the pybind11 install in the current venv.
if(NOT DEFINED Python_EXECUTABLE)
    find_package(Python3 COMPONENTS Interpreter REQUIRED)
endif()

execute_process(
    COMMAND ${Python_EXECUTABLE} -c "import pybind11, sys; sys.stdout.write(pybind11.get_cmake_dir())"
    OUTPUT_VARIABLE pybind11_DIR
    OUTPUT_STRIP_TRAILING_WHITESPACE
)
find_package(pybind11 CONFIG REQUIRED)

# --- Threads + Python dev headers (pybind11 needs the latter) ---------------
find_package(Threads REQUIRED)
find_package(Python3 COMPONENTS Development REQUIRED)

# --- Build the extension module --------------------------------------------
pybind11_add_module(quant_engine_cpp
    bsm_engine.cpp
)

# Link against Python (some pybind11 versions don't do this automatically
# when the user-supplied Python is found via find_package rather than via
# the pybind11 toolchain).
target_link_libraries(quant_engine_cpp PRIVATE Python3::Python)
target_link_libraries(quant_engine_cpp PRIVATE Threads::Threads)

# Sensible warning flags.
if(MSVC)
    target_compile_options(quant_engine_cpp PRIVATE /W4 /permissive-)
else()
    target_compile_options(quant_engine_cpp PRIVATE -Wall -Wextra -Wpedantic)
endif()

# Place the compiled module at the project root of cpp_core/ so a
# one-line `sys.path.insert(0, "cpp_core")` in main.py makes
# `import quant_engine_cpp` work.
set_target_properties(quant_engine_cpp PROPERTIES
    LIBRARY_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}"
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_SOURCE_DIR}"
)
