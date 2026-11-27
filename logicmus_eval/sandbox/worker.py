"""Private JSON worker entry point. This is not a hostile-Python sandbox."""

import contextlib
import json
import os
import sys
from typing import cast

from logicmus_eval.models.evaluation import Z3ExecutionResult
from logicmus_eval.sandbox.bounded_output import BoundedOutput
from logicmus_eval.sandbox.deadline import remaining_milliseconds
from logicmus_eval.sandbox.namespace import code_namespace
from logicmus_eval.sandbox.protocol import WorkerRequest
from logicmus_eval.sandbox.result_building import exception_result
from logicmus_eval.sandbox.solver_registry import SolverRegistry
from logicmus_eval.sandbox.verification import verify_formulas


def run_code(code: str, expected_ids: list[str], deadline: float) -> Z3ExecutionResult:
    output: BoundedOutput = BoundedOutput()
    result: Z3ExecutionResult
    is_sat: bool
    core: list[str]
    exc: BaseException
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            remaining_milliseconds(deadline)
            registry: SolverRegistry = SolverRegistry(expected_ids, deadline)
            namespace: dict[str, object] = code_namespace(registry)
            # One namespace is essential for functions and comprehensions.
            exec(code, namespace, namespace)  # noqa: S102  # pylint: disable=exec-used
            registry.validate(namespace)
            is_sat, core = verify_formulas(registry.formulas, deadline)
            result = Z3ExecutionResult(success=True, is_sat=is_sat, conflict_core=core)
    # Generated SystemExit/KeyboardInterrupt must not abort the parent run.
    except BaseException as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
        result = exception_result(exc)
    result.diagnostics = output.getvalue()
    return result


def main() -> None:
    request: WorkerRequest = cast(WorkerRequest, json.load(sys.stdin.buffer))
    result: Z3ExecutionResult = run_code(
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
