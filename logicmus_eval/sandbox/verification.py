"""Trusted SAT and subset-minimal MUS checks, independent of generated code."""

from collections.abc import Sequence

import z3  # type: ignore[import-untyped]

from logicmus_eval.sandbox.deadline import remaining_milliseconds
from logicmus_eval.sandbox.errors import SolverUnknownError


def checked_solver(
    formulas: Sequence[z3.BoolRef], deadline: float
) -> tuple[z3.Solver, z3.CheckSatResult]:
    """No tracking literals or removed assertions survive into this check."""
    solver: z3.Solver = z3.Solver()
    solver.set(timeout=remaining_milliseconds(deadline))
    solver.add(*formulas)
    result: z3.CheckSatResult = solver.check()
    remaining_milliseconds(deadline)
    if result == z3.unknown:
        raise SolverUnknownError(f"Solver returned unknown: {solver.reason_unknown()}")
    return solver, result


def verify_formulas(
    formulas: dict[str, z3.BoolRef], deadline: float
) -> tuple[bool, list[str]]:
    """Deletion-minimize the full candidate, then independently recheck it."""
    candidate: list[str] = sorted(formulas)

    def check(ids: list[str]) -> z3.CheckSatResult:
        return checked_solver([formulas[key] for key in ids], deadline)[1]

    if check(candidate) == z3.sat:
        return True, []
    key: str
    for key in sorted(formulas):
        reduced: list[str] = [item for item in candidate if item != key]
        if check(reduced) == z3.unsat:
            candidate = reduced
    if check(candidate) != z3.unsat:
        raise SolverUnknownError("Could not verify UNSAT core")
    for key in candidate:
        if check([item for item in candidate if item != key]) != z3.sat:
            raise SolverUnknownError("Could not verify core minimality")
    return False, candidate
