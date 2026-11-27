"""Append-only Solver facade exposed to generated Python."""

from __future__ import annotations

from typing import TYPE_CHECKING, Never

import z3  # type: ignore[import-untyped]

from logicmus_eval.sandbox.verification import checked_solver

if TYPE_CHECKING:
    from logicmus_eval.sandbox.solver_registry import SolverRegistry


class ControlledSolver:
    """Append-only registration and read-only observations, no native handle."""

    def __init__(self, registry: SolverRegistry) -> None:
        self._registry: SolverRegistry = registry
        self._last_solver: z3.Solver | None = None
        self._last_result: z3.CheckSatResult | None = None

    def assert_and_track(self, formula: z3.BoolRef | bool, rule_id: str) -> None:
        registry: SolverRegistry = self._registry
        if not isinstance(rule_id, str):
            registry.reject("Tracking ID must be a string")
        if rule_id not in registry.expected:
            registry.reject(f"Unknown rule ID: {rule_id}")
        if rule_id in registry.formulas:
            registry.reject(f"Duplicate rule ID: {rule_id}")
        normalized: z3.BoolRef = (
            z3.BoolVal(formula) if isinstance(formula, bool) else formula
        )
        if not z3.is_bool(normalized):
            registry.reject(f"Rule {rule_id} must register one Boolean formula")
        if normalized.ctx != z3.main_ctx():
            registry.reject("Only the worker's default Z3 context is supported")
        registry.formulas[rule_id] = normalized
        self._last_solver = self._last_result = None

    def check(self, *args: object, **kwargs: object) -> z3.CheckSatResult:
        if args or kwargs:
            self._registry.reject("Solver.check() does not support assumptions")
        self._last_solver, self._last_result = checked_solver(
            list(self._registry.formulas.values()), self._registry.deadline
        )
        return self._last_result

    def unsat_core(self) -> list[z3.BoolRef]:
        if self._last_result != z3.unsat:
            self._registry.reject("unsat_core() requires a preceding UNSAT check")
        # Compatibility candidate only; trusted minimization never consumes it.
        return [z3.Bool(key) for key in sorted(self._registry.formulas)]

    def model(self) -> z3.ModelRef:
        if self._last_result != z3.sat or self._last_solver is None:
            self._registry.reject("model() requires a preceding SAT check")
        return self._last_solver.model()

    def assertions(self) -> list[z3.BoolRef]:
        return list(self._registry.formulas.values())

    def reason_unknown(self) -> str:
        return ""  # unknown raises instead of producing a model-visible verdict

    def __getattr__(self, name: str) -> Never:
        self._registry.reject(f"Unsupported Solver operation: {name}")

    def __iadd__(self, _formula: object) -> Never:
        self._registry.reject("Untracked Solver += is unsupported")
