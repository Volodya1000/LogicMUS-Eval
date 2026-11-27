"""Private JSON worker entry point. This is not a hostile-Python sandbox."""

import builtins
import contextlib
import io
import json
import math
import os
import sys
from types import ModuleType
from typing import Any

import z3  # type: ignore[import-untyped]

from logicmus_eval.enums import EvaluationErrorType
from logicmus_eval.models.evaluation import Z3ExecutionResult
from logicmus_eval.sandbox.controlled_solver import (
    ContractError,
    SolverRegistry,
    SolverUnknownError,
    remaining_milliseconds,
    verify_formulas,
)

DIAGNOSTIC_LIMIT = 8192

# Expression-only facade: no raw solver, tactics, global settings, Z3 C API,
# nested modules, contexts or file/SMT parsers. Imports cannot bypass Solver().
EXPRESSION_NAMES = [
    "Bool",
    "Bools",
    "BoolVal",
    "BoolRef",
    "Int",
    "Ints",
    "IntVal",
    "Real",
    "Reals",
    "RealVal",
    "ArithRef",
    "BitVec",
    "BitVecs",
    "BitVecVal",
    "BitVecRef",
    "String",
    "Strings",
    "StringVal",
    "StringSort",
    "BoolSort",
    "IntSort",
    "RealSort",
    "BitVecSort",
    "Array",
    "ArraySort",
    "Select",
    "Store",
    "K",
    "And",
    "Or",
    "Not",
    "Implies",
    "If",
    "Xor",
    "Distinct",
    "Sum",
    "Product",
    "Abs",
    "ToReal",
    "ToInt",
    "IsInt",
    "ForAll",
    "Exists",
    "Function",
    "Const",
    "Consts",
    "FreshBool",
    "FreshInt",
    "FreshReal",
    "DeclareSort",
    "Datatype",
    "EnumSort",
    "SetSort",
    "EmptySet",
    "FullSet",
    "SetAdd",
    "SetDel",
    "SetUnion",
    "SetIntersect",
    "SetDifference",
    "IsMember",
    "IsSubset",
    "PbEq",
    "PbLe",
    "PbGe",
    "AtMost",
    "AtLeast",
    "Concat",
    "Extract",
    "ZeroExt",
    "SignExt",
    "ULT",
    "ULE",
    "UGT",
    "UGE",
    "LShR",
    "Length",
    "Contains",
    "PrefixOf",
    "SuffixOf",
    "IndexOf",
    "SubString",
    "Replace",
    "IntToStr",
    "StrToInt",
    "simplify",
    "substitute",
    "is_true",
    "is_false",
    "is_bool",
    "is_int",
    "is_real",
    "sat",
    "unsat",
    "unknown",
]

BUILTIN_NAMES = [
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "enumerate",
    "filter",
    "float",
    "int",
    "len",
    "list",
    "map",
    "max",
    "min",
    "print",
    "range",
    "reversed",
    "round",
    "set",
    "sorted",
    "str",
    "sum",
    "tuple",
    "zip",
    "Exception",
    "ValueError",
    "TypeError",
    "RuntimeError",
    "SystemExit",
    "KeyboardInterrupt",
]


class BoundedOutput(io.TextIOBase):
    """Discard diagnostic overflow while reporting successful writes to print."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.size = 0

    def write(self, text: str) -> int:
        part = text[: max(0, DIAGNOSTIC_LIMIT - self.size)]
        if part:
            self.parts.append(part)
        self.size += len(part)
        return len(text)

    def getvalue(self) -> str:
        return "".join(self.parts)


def code_namespace(registry: SolverRegistry) -> dict[str, Any]:
    facade = ModuleType("z3")
    for name in EXPRESSION_NAMES:
        setattr(facade, name, getattr(z3, name))
    facade.__dict__["Solver"] = registry.create

    def unsupported(name: str) -> Any:
        return registry.reject(f"Unsupported z3 API: {name}")

    facade.__dict__["__getattr__"] = unsupported
    exports = [*EXPRESSION_NAMES, "Solver"]
    facade.__dict__["__all__"] = exports

    def safe_import(
        name: str,
        _globals: Any = None,
        _locals: Any = None,
        _fromlist: Any = (),
        level: int = 0,
    ) -> Any:
        if not level and name == "z3":
            return facade
        if not level and name == "math":
            return math
        if name.startswith("z3."):
            return registry.reject(f"Unsupported z3 import: {name}")
        raise ImportError(f"Importing '{name}' is forbidden in sandbox")

    safe_builtins = {name: getattr(builtins, name) for name in BUILTIN_NAMES}
    safe_builtins["__import__"] = safe_import
    namespace = {name: getattr(facade, name) for name in exports}
    # Give unsupported constructor aliases classified contract diagnostics too.
    namespace["SolverFor"] = lambda *a, **kw: unsupported("SolverFor")
    namespace["SimpleSolver"] = lambda *a, **kw: unsupported("SimpleSolver")
    namespace.update({"__builtins__": safe_builtins, "z3": facade})
    return namespace


def run_code(code: str, expected_ids: list[str], deadline: float) -> Z3ExecutionResult:
    output = BoundedOutput()
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            remaining_milliseconds(deadline)
            registry = SolverRegistry(expected_ids, deadline)
            namespace = code_namespace(registry)
            # One namespace is essential for functions and comprehensions.
            exec(code, namespace, namespace)  # noqa: S102  # pylint: disable=exec-used
            registry.validate(namespace)
            is_sat, core = verify_formulas(registry.formulas, deadline)
            result = Z3ExecutionResult(success=True, is_sat=is_sat, conflict_core=core)
    # Generated SystemExit/KeyboardInterrupt must not abort the parent run.
    except BaseException as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        kind = EvaluationErrorType.EXEC_ERROR
        if isinstance(exc, ContractError):
            kind = EvaluationErrorType.Z3_CONTRACT_ERROR
        elif isinstance(exc, TimeoutError):
            kind = EvaluationErrorType.Z3_TIMEOUT
        elif isinstance(exc, SolverUnknownError):
            kind = EvaluationErrorType.Z3_SOLVER_UNKNOWN
        result = Z3ExecutionResult(
            success=False,
            error_type=kind,
            error=f"{type(exc).__name__}: {exc}"[:DIAGNOSTIC_LIMIT],
        )
    result.diagnostics = output.getvalue()
    return result


def main() -> None:
    request = json.load(sys.stdin.buffer)
    result = run_code(
        request["code"], request["expected_rule_ids"], request["deadline"]
    )
    sys.stdout.buffer.write(result.model_dump_json().encode("utf-8"))
    sys.stdout.buffer.flush()
    # CPython on Windows can retain its interrupted-exit status even after a
    # generated KeyboardInterrupt is caught. The JSON result owns that error;
    # exit normally after flushing, without running generated finalizers.
    os._exit(0)  # pylint: disable=protected-access


if __name__ == "__main__":
    main()
