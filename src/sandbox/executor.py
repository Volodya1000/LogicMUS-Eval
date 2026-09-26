import re
import threading
import time
from typing import Any

import z3  # type: ignore

from src.models.evaluation import Z3ExecutionResult

ALLOWED_MODULES = {"z3", "z3.z3", "math"}


def _safe_import(
    name: str,
    globals_dict: dict[str, Any] | None = None,
    locals_dict: dict[str, Any] | None = None,
    fromlist: tuple[str, ...] = (),
    level: int = 0,
) -> Any:
    if name in ALLOWED_MODULES or name.startswith("z3."):
        return __import__(name, globals_dict, locals_dict, fromlist, level)
    raise ImportError(f"Importing '{name}' is forbidden in sandbox")


SAFE_BUILTINS = {
    "__import__": _safe_import,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "print": print,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


def clean_markdown_code(code_str: str) -> str:
    cleaned = code_str.strip()
    match = re.search(r"```(?:python)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    if match:
        return match.group(1).strip()
    return cleaned


class Z3CodeExecutor:
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self.timeout_seconds = timeout_seconds

    def execute(self, code_str: str) -> Z3ExecutionResult:
        cleaned_code = clean_markdown_code(code_str)

        globals_env: dict[str, Any] = {
            "__builtins__": SAFE_BUILTINS,
            "z3": z3,
            "Solver": z3.Solver,
            "Bool": z3.Bool,
            "Bools": z3.Bools,
            "Int": z3.Int,
            "Ints": z3.Ints,
            "Real": z3.Real,
            "Reals": z3.Reals,
            "And": z3.And,
            "Or": z3.Or,
            "Not": z3.Not,
            "Implies": z3.Implies,
            "sat": z3.sat,
            "unsat": z3.unsat,
            "unknown": z3.unknown,
        }
        locals_env: dict[str, Any] = {}
        exception_holder: list[BaseException] = []

        start_time = time.perf_counter()

        def _runner() -> None:
            try:
                exec(  # noqa: S102  # pylint: disable=exec-used
                    cleaned_code, globals_env, locals_env
                )
            except BaseException as ex:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                exception_holder.append(ex)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=self.timeout_seconds)

        if thread.is_alive():
            return Z3ExecutionResult(
                success=False,
                error=f"Execution timed out after {self.timeout_seconds} seconds",
                execution_time=self.timeout_seconds,
            )

        exec_time = time.perf_counter() - start_time

        if exception_holder:
            e = exception_holder[0]
            if isinstance(e, SyntaxError):
                return Z3ExecutionResult(
                    success=False,
                    error=f"SyntaxError in generated code: {e}",
                    execution_time=exec_time,
                )
            return Z3ExecutionResult(
                success=False,
                error=f"Runtime error: {type(e).__name__}: {e}",
                execution_time=exec_time,
            )

        return self._extract_results(locals_env, exec_time)

    def _extract_results(
        self, locals_env: dict[str, Any], exec_time: float
    ) -> Z3ExecutionResult:
        is_sat: bool | None = None
        conflict_core: list[str] = []

        if "is_sat" in locals_env and isinstance(locals_env["is_sat"], bool):
            is_sat = locals_env["is_sat"]

        solver_obj = locals_env.get("solver")
        if isinstance(solver_obj, z3.Solver):
            if is_sat is None:
                check_result = solver_obj.check()
                if check_result == z3.sat:
                    is_sat = True
                elif check_result == z3.unsat:
                    is_sat = False

            if is_sat is False and "conflict_core" not in locals_env:
                conflict_core = [str(clause) for clause in solver_obj.unsat_core()]

        if "conflict_core" in locals_env and isinstance(
            locals_env["conflict_core"], (list, set, tuple)
        ):
            conflict_core = [str(item) for item in locals_env["conflict_core"]]

        if is_sat is None:
            return Z3ExecutionResult(
                success=False,
                error="Could not resolve 'is_sat' or detect solver check result in code scope",
                execution_time=exec_time,
            )

        return Z3ExecutionResult(
            success=True,
            is_sat=is_sat,
            conflict_core=conflict_core,
            execution_time=exec_time,
        )
