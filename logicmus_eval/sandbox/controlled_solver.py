"""Record model assertions and verify them with fresh, trusted Z3 solvers."""

import math
import time
from collections.abc import Sequence
from typing import Any, Never

import z3  # type: ignore[import-untyped]


class ContractError(Exception):
    """The generated program does not implement the supported contract."""


class SolverUnknownError(Exception):
    """A required SMT check could not establish SAT or UNSAT."""


def remaining_milliseconds(deadline: float) -> int:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Z3 execution deadline exhausted")
    return max(1, min(2**31 - 1, math.ceil(remaining * 1000)))


def checked_solver(formulas: Sequence[Any], deadline: float) -> tuple[Any, Any]:
    """No tracking literals or removed assertions survive into this check."""
    solver = z3.Solver()
    solver.set(timeout=remaining_milliseconds(deadline))
    solver.add(*formulas)
    result = solver.check()
    remaining_milliseconds(deadline)
    if result == z3.unknown:
        raise SolverUnknownError(f"Solver returned unknown: {solver.reason_unknown()}")
    return solver, result


def verify_formulas(
    formulas: dict[str, Any], deadline: float
) -> tuple[bool, list[str]]:
    """Deletion-minimize the full candidate, then independently recheck it."""
    candidate = sorted(formulas)

    def check(ids: list[str]) -> Any:
        return checked_solver([formulas[key] for key in ids], deadline)[1]

    if check(candidate) == z3.sat:
        return True, []
    for key in sorted(formulas):
        reduced = [item for item in candidate if item != key]
        if check(reduced) == z3.unsat:
            candidate = reduced
    if check(candidate) != z3.unsat:
        raise SolverUnknownError("Could not verify UNSAT core")
    for key in candidate:
        if check([item for item in candidate if item != key]) != z3.sat:
            raise SolverUnknownError("Could not verify core minimality")
    return False, candidate


class SolverRegistry:
    """One target solver; a rejected operation permanently invalidates the run."""

    def __init__(self, expected_ids: list[str], deadline: float) -> None:
        if any(not isinstance(key, str) for key in expected_ids):
            raise ContractError("Expected rule IDs must be strings")
        if len(set(expected_ids)) != len(expected_ids):
            raise ContractError("Expected rule IDs must be unique")
        self.expected = set(expected_ids)
        self.deadline = deadline
        self.formulas: dict[str, Any] = {}
        self.target: ControlledSolver | None = None
        self.violation: str | None = None

    def reject(self, message: str) -> Never:
        self.violation = self.violation or message
        raise ContractError(message)

    def create(self, *args: Any, **kwargs: Any) -> "ControlledSolver":
        if args or kwargs:
            self.reject("Only Solver() without arguments is supported")
        if self.target is not None:
            self.reject("Exactly one Solver() is supported")
        self.target = ControlledSolver(self)
        return self.target

    def validate(self, namespace: dict[str, Any]) -> None:
        if self.violation:
            raise ContractError(self.violation)
        if self.target is None or namespace.get("solver") is not self.target:
            raise ContractError("Program must bind solver = Solver()")
        missing = self.expected - self.formulas.keys()
        if missing:
            raise ContractError(f"Missing rule IDs: {sorted(missing)}")


class ControlledSolver:
    """Append-only registration and read-only observations, no native handle."""

    def __init__(self, registry: SolverRegistry) -> None:
        self._registry = registry
        self._last_solver: Any = None
        self._last_result: Any = None

    def assert_and_track(self, formula: Any, rule_id: str) -> None:
        registry = self._registry
        if not isinstance(rule_id, str):
            registry.reject("Tracking ID must be a string")
        if rule_id not in registry.expected:
            registry.reject(f"Unknown rule ID: {rule_id}")
        if rule_id in registry.formulas:
            registry.reject(f"Duplicate rule ID: {rule_id}")
        if isinstance(formula, bool):
            formula = z3.BoolVal(formula)
        if not z3.is_bool(formula):
            registry.reject(f"Rule {rule_id} must register one Boolean formula")
        if formula.ctx != z3.main_ctx():
            registry.reject("Only the worker's default Z3 context is supported")
        registry.formulas[rule_id] = formula
        self._last_solver = self._last_result = None

    def check(self, *args: Any, **kwargs: Any) -> Any:
        if args or kwargs:
            self._registry.reject("Solver.check() does not support assumptions")
        self._last_solver, self._last_result = checked_solver(
            list(self._registry.formulas.values()), self._registry.deadline
        )
        return self._last_result

    def unsat_core(self) -> list[Any]:
        if self._last_result != z3.unsat:
            self._registry.reject("unsat_core() requires a preceding UNSAT check")
        # Compatibility candidate only; trusted minimization never consumes it.
        return [z3.Bool(key) for key in sorted(self._registry.formulas)]

    def model(self) -> Any:
        if self._last_result != z3.sat:
            self._registry.reject("model() requires a preceding SAT check")
        return self._last_solver.model()

    def assertions(self) -> list[Any]:
        return list(self._registry.formulas.values())

    def reason_unknown(self) -> str:
        return ""  # unknown raises instead of producing a model-visible verdict

    def __getattr__(self, name: str) -> Any:
        return self._registry.reject(f"Unsupported Solver operation: {name}")

    def __iadd__(self, _formula: Any) -> Never:
        self._registry.reject("Untracked Solver += is unsupported")
