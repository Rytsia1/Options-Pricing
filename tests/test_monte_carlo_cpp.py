"""Tests for the optional C++ ``quant_engine_cpp`` extension.

All tests in this module are skipped automatically if the C++ extension
is not built (see ``cpp_core/build_instructions.md``). This keeps the
default CI run green — the existing 51 tests still pass on machines
without MSVC.

To run these tests, build the C++ extension first::

    cd cpp_core
    cmake -S . -B build -G "Visual Studio 17 2022" -A x64
    cmake --build build --config Release --parallel
    cd ..

Then run::

    pytest tests/test_monte_carlo_cpp.py -v
"""

from __future__ import annotations

import pathlib
import sys

import pytest

from src.black_scholes import EuropeanOption


# ---------------------------------------------------------------------- #
# Skip-by-default guard
# ---------------------------------------------------------------------- #
def _cpp_available() -> bool:
    """Return True iff the compiled ``quant_engine_cpp`` can be imported."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    cpp_dir = repo_root / "cpp_core"
    if not cpp_dir.exists():
        return False
    sys.path.insert(0, str(cpp_dir))
    try:
        import quant_engine_cpp  # type: ignore[import-not-found]
        return hasattr(quant_engine_cpp, "MonteCarloPricerCpp")
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _cpp_available(),
    reason=(
        "quant_engine_cpp extension not built. "
        "See cpp_core/build_instructions.md to build it."
    ),
)


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
SCENARIO: dict[str, float] = {
    "S": 100.0, "K": 100.0, "T": 1.0, "r": 0.05, "sigma": 0.20,
}


def _import_cpp():
    """Re-import the C++ module (after sys.path tweak)."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(repo_root / "cpp_core"))
    import quant_engine_cpp  # type: ignore[import-not-found]
    return quant_engine_cpp


# ---------------------------------------------------------------------- #
# Tests
# ---------------------------------------------------------------------- #
def test_cpp_module_imports() -> None:
    cpp = _import_cpp()
    assert hasattr(cpp, "MonteCarloPricerCpp")


def test_cpp_threads_used_at_least_one() -> None:
    cpp = _import_cpp()
    p = cpp.MonteCarloPricerCpp(
        SCENARIO["S"], SCENARIO["K"], SCENARIO["T"],
        SCENARIO["r"], SCENARIO["sigma"],
        10_000, 1, "call", seed=1, antithetic=False, n_threads=0,
    )
    assert p.threads_used() >= 1


def test_cpp_price_returns_four_tuple() -> None:
    cpp = _import_cpp()
    p = cpp.MonteCarloPricerCpp(
        SCENARIO["S"], SCENARIO["K"], SCENARIO["T"],
        SCENARIO["r"], SCENARIO["sigma"],
        10_000, 1, "call", seed=2, antithetic=False, n_threads=0,
    )
    out = p.price()
    assert len(out) == 4
    price, se, ci_lo, ci_hi = out
    assert price > 0
    assert se > 0
    assert ci_lo <= price <= ci_hi


def test_cpp_reproducible_with_seed() -> None:
    """Same seed → same price (per-thread mt19937_64 is deterministic)."""
    cpp = _import_cpp()
    p1 = cpp.MonteCarloPricerCpp(
        SCENARIO["S"], SCENARIO["K"], SCENARIO["T"],
        SCENARIO["r"], SCENARIO["sigma"],
        20_000, 1, "call", seed=42, antithetic=False, n_threads=2,
    )
    p2 = cpp.MonteCarloPricerCpp(
        SCENARIO["S"], SCENARIO["K"], SCENARIO["T"],
        SCENARIO["r"], SCENARIO["sigma"],
        20_000, 1, "call", seed=42, antithetic=False, n_threads=2,
    )
    assert p1.price()[0] == p2.price()[0]


def test_cpp_antithetic_runs() -> None:
    """`antithetic=True` should not crash and should give a finite price."""
    cpp = _import_cpp()
    p = cpp.MonteCarloPricerCpp(
        SCENARIO["S"], SCENARIO["K"], SCENARIO["T"],
        SCENARIO["r"], SCENARIO["sigma"],
        10_000, 1, "call", seed=7, antithetic=True, n_threads=2,
    )
    price, se, ci_lo, ci_hi = p.price()
    assert 0.0 < price < SCENARIO["S"]
    assert ci_lo <= price <= ci_hi


def test_cpp_converges_to_bsm() -> None:
    """At 200k paths the C++ engine is within 1% of the analytical price."""
    cpp = _import_cpp()
    p = cpp.MonteCarloPricerCpp(
        SCENARIO["S"], SCENARIO["K"], SCENARIO["T"],
        SCENARIO["r"], SCENARIO["sigma"],
        200_000, 1, "call", seed=11, antithetic=True, n_threads=0,
    )
    mc_price = p.price()[0]
    bsm_price = EuropeanOption(
        option_type="call",  # type: ignore[arg-type]
        **SCENARIO,
    ).price()
    rel_error = abs(mc_price - bsm_price) / bsm_price
    assert rel_error < 0.01, f"C++ MC={mc_price}, BSM={bsm_price}, rel_error={rel_error}"


def test_cpp_price_both_returns_call_and_put() -> None:
    cpp = _import_cpp()
    p = cpp.MonteCarloPricerCpp(
        SCENARIO["S"], SCENARIO["K"], SCENARIO["T"],
        SCENARIO["r"], SCENARIO["sigma"],
        50_000, 1, "call", seed=3, antithetic=True, n_threads=2,
    )
    call_price, put_price = p.price_both()
    assert 0.0 < call_price < SCENARIO["S"]
    assert 0.0 < put_price < SCENARIO["K"]
    # Put-call parity should hold within a generous tolerance.
    rhs = SCENARIO["S"] - SCENARIO["K"] * 2.718281828459045 ** (
        -SCENARIO["r"] * SCENARIO["T"]
    )
    assert abs((call_price - put_price) - rhs) < 0.5
