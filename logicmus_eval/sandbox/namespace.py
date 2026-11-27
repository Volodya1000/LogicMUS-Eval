"""Build the generated-code namespace without exposing native solver factories."""

import builtins
import math
from types import ModuleType
from typing import Never

import z3  # type: ignore[import-untyped]

from logicmus_eval.sandbox.allowed_names import BUILTIN_NAMES, EXPRESSION_NAMES
from logicmus_eval.sandbox.solver_registry import SolverRegistry


def code_namespace(registry: SolverRegistry) -> dict[str, object]:
    facade: ModuleType = ModuleType("z3")
    name: str
    for name in EXPRESSION_NAMES:
        setattr(facade, name, getattr(z3, name))
    facade.__dict__["Solver"] = registry.create

    def unsupported(name: str) -> Never:
        registry.reject(f"Unsupported z3 API: {name}")

    facade.__dict__["__getattr__"] = unsupported
    exports: list[str] = [*EXPRESSION_NAMES, "Solver"]
    facade.__dict__["__all__"] = exports

    def safe_import(
        name: str,
        _globals: dict[str, object] | None = None,
        _locals: dict[str, object] | None = None,
        _fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> ModuleType:
        if not level and name == "z3":
            return facade
        if not level and name == "math":
            return math
        if name.startswith("z3."):
            return registry.reject(f"Unsupported z3 import: {name}")
        raise ImportError(f"Importing '{name}' is forbidden in sandbox")

    safe_builtins: dict[str, object] = {
        name: getattr(builtins, name) for name in BUILTIN_NAMES
    }
    safe_builtins["__import__"] = safe_import
    namespace: dict[str, object] = {name: getattr(facade, name) for name in exports}

    # Give unsupported constructor aliases classified contract diagnostics too.
    def unsupported_factory(*_args: object, **_kwargs: object) -> Never:
        registry.reject("Unsupported alternate Solver constructor")

    namespace["SolverFor"] = unsupported_factory
    namespace["SimpleSolver"] = unsupported_factory
    namespace.update({"__builtins__": safe_builtins, "z3": facade})
    return namespace
