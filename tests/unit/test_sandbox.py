from src.sandbox.executor import Z3CodeExecutor


def test_sandbox_executes_valid_sat_code():
    code = """
from z3 import Solver, Bool, sat

solver = Solver()
a = Bool('a')
b = Bool('b')
solver.add(a)
solver.add(b)

is_sat = (solver.check() == sat)
conflict_core = []
"""
    executor = Z3CodeExecutor(timeout_seconds=2.0)
    result = executor.execute(code)

    assert result.success is True
    assert result.is_sat is True
    assert result.conflict_core == []


def test_sandbox_executes_unsat_code_with_core():
    code = """
from z3 import Solver, Bool, sat

solver = Solver()
a = Bool('a')
solver.assert_and_track(a, 'R1')
solver.assert_and_track(a == False, 'R2')

is_sat = (solver.check() == sat)
conflict_core = [str(c) for c in solver.unsat_core()]
"""
    executor = Z3CodeExecutor(timeout_seconds=2.0)
    result = executor.execute(code)

    assert result.success is True
    assert result.is_sat is False
    assert set(result.conflict_core) == {"R1", "R2"}


def test_sandbox_intercepts_syntax_error():
    code = "this is an invalid python code!"
    executor = Z3CodeExecutor(timeout_seconds=2.0)
    result = executor.execute(code)

    assert result.success is False
    assert "SyntaxError" in result.error


def test_sandbox_prevents_unsafe_operations():
    code = """
import os
os.listdir('.')
"""
    executor = Z3CodeExecutor(timeout_seconds=2.0)
    result = executor.execute(code)

    assert result.success is False


def test_sandbox_handles_timeout():
    code = """
while True:
    pass
"""
    executor = Z3CodeExecutor(timeout_seconds=0.5)
    result = executor.execute(code)

    assert result.success is False
    assert "timed out" in result.error
