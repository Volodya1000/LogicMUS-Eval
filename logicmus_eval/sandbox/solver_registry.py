"""Registration contract and factory for the sole target Solver."""

from typing import Never

import z3  # type: ignore[import-untyped]

from logicmus_eval.sandbox.controlled_solver import ControlledSolver
from logicmus_eval.sandbox.errors import ContractError


class SolverRegistry:
    """One target solver; a rejected operation permanently invalidates the run."""

    def __init__(self, expected_ids: list[str], deadline: float) -> None:
        if any(not isinstance(key, str) for key in expected_ids):
            raise ContractError("Expected rule IDs must be strings")
        if len(set(expected_ids)) != len(expected_ids):
            raise ContractError("Expected rule IDs must be unique")
        self.expected: set[str] = set(expected_ids)
        self.deadline: float = deadline
        self.formulas: dict[str, z3.BoolRef] = {}
        self.target: ControlledSolver | None = None
        self.violation: str | None = None

    def reject(self, message: str) -> Never:
        self.violation = self.violation or message
        raise ContractError(message)

    def create(self, *args: object, **kwargs: object) -> ControlledSolver:
        if args or kwargs:
            self.reject("Only Solver() without arguments is supported")
        if self.target is not None:
            self.reject("Exactly one Solver() is supported")
        self.target = ControlledSolver(self)
        return self.target

    def validate(self, namespace: dict[str, object]) -> None:
        if self.violation:
            raise ContractError(self.violation)
        if self.target is None or namespace.get("solver") is not self.target:
            raise ContractError("Program must bind solver = Solver()")
        missing: set[str] = self.expected - self.formulas.keys()
        if missing:
            raise ContractError(f"Missing rule IDs: {sorted(missing)}")
