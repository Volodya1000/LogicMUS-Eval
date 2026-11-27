"""Independent minimizer checks, including required checks returning unknown."""

import time

import pytest
import z3

from logicmus_eval.sandbox.controlled_solver import (
    SolverUnknownError,
    verify_formulas,
)
from tests.unit.test_isolated_sandbox import independently_verify


def test_minimizer_starts_from_known_nonminimal_candidate(monkeypatch):
    def forbidden_core(_solver):
        raise AssertionError("Must not rely on unsat_core heuristics")

    monkeypatch.setattr(z3.Solver, "unsat_core", forbidden_core)
    x, y = z3.Bools("x y")
    is_sat, core = verify_formulas(
        {"R3": y, "R2": z3.Not(x), "R1": x}, time.monotonic() + 10
    )
    assert is_sat is False and core == ["R1", "R2"]
    independently_verify(core)


@pytest.mark.parametrize("unknown_at", [1, 2, 5, 6])
def test_unknown_at_initial_deletion_or_verification_is_not_mus(
    monkeypatch, unknown_at
):
    calls = 0
    real_check = z3.Solver.check

    def check(solver, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == unknown_at:
            return z3.unknown
        return real_check(solver, *args, **kwargs)

    monkeypatch.setattr(z3.Solver, "check", check)
    x, y = z3.Bools("x y")
    with pytest.raises(SolverUnknownError):
        verify_formulas({"R1": x, "R2": z3.Not(x), "R3": y}, time.monotonic() + 10)


def test_deadline_covers_minimization(monkeypatch):
    real_check = z3.Solver.check
    calls = 0

    def check(solver, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            time.sleep(0.1)
        return real_check(solver, *args, **kwargs)

    monkeypatch.setattr(z3.Solver, "check", check)
    x = z3.Bool("x")
    with pytest.raises(TimeoutError):
        verify_formulas({"R1": x, "R2": z3.Not(x)}, time.monotonic() + 0.05)


def test_empty_registered_set_is_sat():
    assert verify_formulas({}, time.monotonic() + 10) == (True, [])
