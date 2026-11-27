from logicmus_eval.models.evaluation import Z3ExecutionResult
from logicmus_eval.sandbox.executor import Z3CodeExecutor


def test_sandbox_executes_valid_sat_code() -> None:
    code: str = """
from z3 import Solver, Bool, sat

solver = Solver()
a = Bool('a')
b = Bool('b')
solver.assert_and_track(a, 'R1')
solver.assert_and_track(b, 'R2')

is_sat = (solver.check() == sat)
conflict_core = []
"""
    executor: Z3CodeExecutor = Z3CodeExecutor(timeout_seconds=10.0)
    result: Z3ExecutionResult = executor.execute(code, ["R1", "R2"])

    assert result.success is True
    assert result.is_sat is True
    assert result.conflict_core == []


def test_sandbox_executes_unsat_code_with_core() -> None:
    code: str = """

solver = Solver()
a = Bool('a')
solver.assert_and_track(a, 'R1')
solver.assert_and_track(a == False, 'R2')

is_sat = (solver.check() == sat)
conflict_core = [str(c) for c in solver.unsat_core()]
"""
    executor: Z3CodeExecutor = Z3CodeExecutor(timeout_seconds=10.0)
    result: Z3ExecutionResult = executor.execute(code, ["R1", "R2"])

    assert result.success is True
    assert result.is_sat is False
    assert set(result.conflict_core) == {"R1", "R2"}


def test_sandbox_prevents_unsafe_operations() -> None:
    code: str = """
import os
os.listdir('.')
"""
    executor: Z3CodeExecutor = Z3CodeExecutor(timeout_seconds=2.0)
    result: Z3ExecutionResult = executor.execute(code, [])

    assert result.success is False


def test_sandbox_intercepts_syntax_error() -> None:
    code: str = "this is an invalid python code!"
    executor: Z3CodeExecutor = Z3CodeExecutor(timeout_seconds=2.0)
    result: Z3ExecutionResult = executor.execute(code, [])

    assert result.success is False
    error_msg = result.error or ""
    assert "SyntaxError" in error_msg


def test_sandbox_handles_timeout() -> None:
    code: str = """
while True:
    pass
"""
    executor: Z3CodeExecutor = Z3CodeExecutor(timeout_seconds=0.5)
    result: Z3ExecutionResult = executor.execute(code, [])

    assert result.success is False
    error_msg = result.error or ""
    assert "timed out" in error_msg
