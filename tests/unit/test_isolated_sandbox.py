"""Offline executor regressions; real processes and independent SMT checks."""

import subprocess
import sys
import time

import pytest
import z3

from logicmus_eval.sandbox.executor import Z3CodeExecutor

SAT_CODE = "solver = Solver(); solver.assert_and_track(Bool('x'), 'R1')"
UNSAT_CODE = """
solver = Solver()
x, y = Bools('x y')
solver.assert_and_track(x, 'R1')
solver.assert_and_track(Not(x), 'R2')
solver.assert_and_track(y, 'R3')
"""


def execute(code, ids=("R1",), timeout=10):
    return Z3CodeExecutor(timeout).execute(code, list(ids))


@pytest.mark.parametrize(
    "prefix",
    [
        "from z3 import Solver, Bool",
        "from z3 import *",
        "import z3\nSolver, Bool = z3.Solver, z3.Bool",
    ],
)
def test_supported_imports_and_sat(prefix):
    result = execute(prefix + "\n" + SAT_CODE + "\nis_sat = False")
    assert result.success and result.is_sat is True
    assert result.conflict_core == []


def test_functions_and_generators_share_namespace():
    result = execute("""
from z3 import *
solver = Solver()
x = Bool('x')
def register():
    solver.assert_and_track(And(v for v in [x]), 'R1')
register()
""")
    assert result.success, result.error


def test_missing_solver_cannot_be_replaced_by_model_verdict():
    result = execute("is_sat = True")
    assert not result.success and result.is_sat is None
    assert result.error_type == "z3_contract_error"


@pytest.mark.parametrize(
    "forged",
    [
        "is_sat = True",
        "is_sat = False; conflict_core = ['fake']",
    ],
)
def test_trusted_unsat_ignores_forged_verdict_and_core(forged):
    result = execute(UNSAT_CODE + "\n" + forged, ["R3", "R2", "R1"])
    assert result.success and result.is_sat is False
    assert result.conflict_core == ["R1", "R2"]
    independently_verify(result.conflict_core)


def independently_verify(core):
    x, y = z3.Bools("x y")
    formulas = {"R1": x, "R2": z3.Not(x), "R3": y, "R4": z3.Not(y)}
    solver = z3.Solver()
    solver.add(*(formulas[key] for key in core))
    assert solver.check() == z3.unsat
    for removed in core:
        solver = z3.Solver()
        solver.add(*(formulas[key] for key in core if key != removed))
        assert solver.check() == z3.sat


@pytest.mark.parametrize(
    "code,ids",
    [
        (SAT_CODE, ["R1", "R2"]),
        (SAT_CODE, ["R2"]),
        (SAT_CODE + "\nsolver.assert_and_track(Bool('y'), 'R1')", ["R1"]),
        (SAT_CODE + "\nsolver.add(True)", ["R1"]),
        (SAT_CODE + '\nsolver += Bool("y")', ["R1"]),
        (SAT_CODE + "\nsolver.push()", ["R1"]),
        (SAT_CODE + "\nsolver.pop()", ["R1"]),
        (SAT_CODE + "\nsolver.reset()", ["R1"]),
        (SAT_CODE + "\nsolver.set(timeout=1)", ["R1"]),
        (SAT_CODE + "\nother = Solver()", ["R1"]),
        ("solver = SolverFor('QF_LIA')", ["R1"]),
        ("solver = SimpleSolver()", ["R1"]),
        ("solver = Solver(); solver.assert_and_track(42, 'R1')", ["R1"]),
        ("solver = Solver(); solver.assert_and_track(True, Bool('R1'))", ["R1"]),
    ],
)
def test_contract_rejects_untrustworthy_registration(code, ids):
    result = execute(code, ids)
    assert not result.success and result.is_sat is None, result
    assert result.error_type == "z3_contract_error", result.error


def test_tracking_symbol_collision_does_not_change_formula_semantics():
    result = execute("""
solver = Solver()
x = Bool('R1')
solver.assert_and_track(Not(x), 'R1')
""")
    assert result.success and result.is_sat is True


def test_catching_contract_exception_does_not_hide_violation():
    result = execute(
        SAT_CODE
        + """
try:
    solver.add(False)
except Exception:
    pass
"""
    )
    assert not result.success and result.error_type == "z3_contract_error"


@pytest.mark.parametrize(
    "expression",
    [
        'z3.SolverFor("QF_LIA")',
        "z3.SimpleSolver()",
        'z3.Tactic("smt").solver()',
        '__import__("z3.z3").Solver()',
    ],
)
def test_imported_module_cannot_supply_uncontrolled_solver(expression):
    result = execute("import z3\nsolver = " + expression)
    assert not result.success and result.error_type == "z3_contract_error"


def test_several_mus_return_one_verified_deterministically():
    code = UNSAT_CODE + "\nsolver.assert_and_track(Not(y), 'R4')"
    first = execute(code, ["R4", "R2", "R3", "R1"])
    second = execute(code, ["R1", "R2", "R3", "R4"])
    assert first.success and second.success
    assert first.conflict_core == second.conflict_core
    independently_verify(first.conflict_core)


@pytest.mark.parametrize(
    "code,kind,message",
    [
        ("is this valid python???", "exec_error", "SyntaxError"),
        ("1 / 0", "exec_error", "ZeroDivisionError"),
        (
            "solver = Solver(); x = Real('x'); solver.assert_and_track(2**x == 3, 'R1')",
            "z3_solver_unknown",
            "unknown",
        ),
        ("raise SystemExit(7)", "exec_error", "SystemExit"),
        ("raise KeyboardInterrupt()", "exec_error", "KeyboardInterrupt"),
    ],
)
def test_nonanswers_are_classified(code, kind, message):
    result = execute(code)
    assert not result.success and result.is_sat is None
    assert result.error_type == kind
    assert message in result.error


def observe_workers(monkeypatch):
    processes = []
    real_popen = subprocess.Popen

    def start(*args, **kwargs):
        # Ownership and bounded cleanup deliberately belong to the executor.
        process = real_popen(*args, **kwargs)  # pylint: disable=consider-using-with
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", start)
    return processes


def test_timeout_reaps_worker_and_next_case_succeeds(monkeypatch):
    processes = observe_workers(monkeypatch)
    result = execute("while True: pass", timeout=2)
    assert not result.success and result.error_type == "z3_timeout"
    assert len(processes) == 1 and processes[0].poll() is not None
    assert processes[0].stdin is None and processes[0].stdout.closed
    assert execute(SAT_CODE).success


def test_abrupt_worker_exit_is_failure_and_next_case_succeeds(monkeypatch):
    real_popen = subprocess.Popen
    processes = []

    def crash(*_args, **kwargs):
        process = real_popen(  # pylint: disable=consider-using-with
            [sys.executable, "-c", "import os; os._exit(17)"], **kwargs
        )
        processes.append(process)
        return process

    with monkeypatch.context() as patch:
        patch.setattr(subprocess, "Popen", crash)
        result = execute(SAT_CODE)
    assert not result.success and result.error_type == "z3_worker_error"
    assert processes[0].poll() == 17
    assert execute(SAT_CODE).success


def test_parent_interrupt_reaps_worker_and_propagates(monkeypatch):
    popen_class = subprocess.Popen
    real_communicate = subprocess.Popen.communicate
    processes = observe_workers(monkeypatch)
    first = True

    def interrupted(self, *args, **kwargs):
        nonlocal first
        if first:
            first = False
            raise KeyboardInterrupt
        return real_communicate(self, *args, **kwargs)

    monkeypatch.setattr(popen_class, "communicate", interrupted)
    with pytest.raises(KeyboardInterrupt):
        execute("while True: pass")
    assert len(processes) == 1 and processes[0].poll() is not None
    assert processes[0].stdin is None and processes[0].stdout.closed


def test_stdout_and_error_diagnostics_are_bounded():
    result = execute("for i in range(10000): print('x' * 2000)\n" + SAT_CODE)
    assert result.success
    assert len(result.diagnostics) <= 8192
    failed = execute("int('x' * 1000000)")
    assert not failed.success and len(failed.error) <= 8192


def test_large_ipc_result_is_drained_before_waiting():
    # A one-member MUS with an ID much larger than a Windows pipe buffer.
    label = "R" * 200000
    result = execute(
        f"solver = Solver(); solver.assert_and_track(False, {label!r})", [label]
    )
    assert result.success and result.is_sat is False
    assert result.conflict_core == [label]


def test_startup_is_inside_deadline(monkeypatch):
    real_popen = subprocess.Popen
    processes = []

    def slow_start(*args, **kwargs):
        time.sleep(0.1)
        process = real_popen(*args, **kwargs)  # pylint: disable=consider-using-with
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", slow_start)
    result = execute(SAT_CODE, timeout=0.01)
    assert not result.success and result.error_type == "z3_timeout"
    assert processes[0].poll() is not None


def test_large_request_cannot_block_deadline_when_worker_never_reads(monkeypatch):
    real_popen = subprocess.Popen
    processes = []

    def unread(*_args, **kwargs):
        # The finite sleep also makes a regression fail instead of hanging CI.
        process = real_popen(  # pylint: disable=consider-using-with
            [
                getattr(sys, "_base_executable", sys.executable),
                "-c",
                "import time; time.sleep(8)",
            ],
            **kwargs,
        )
        processes.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", unread)
    result = execute("#" + "x" * 1000000, timeout=2)
    assert not result.success and result.error_type == "z3_timeout"
    assert processes[0].poll() is not None
    assert processes[0].returncode != 0  # deadline killed it before its normal exit


def test_unicode_ipc_ignores_inherited_locale_encoding(monkeypatch):
    monkeypatch.setenv("PYTHONUTF8", "0")
    monkeypatch.setenv("PYTHONIOENCODING", "cp1251")
    result = execute(
        "solver = Solver(); solver.assert_and_track(False, '一'); print('Ж')", ["一"]
    )
    assert result.success and result.conflict_core == ["一"]
    assert result.diagnostics == "Ж\n"
