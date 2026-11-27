# Isolated Z3 execution and verified MUS

**Goal:** implement the supplied isolate-z3-and-verify-mus specification on
master 7ddff9f, preserving PR #2/#3, without LLM calls or historical edits.

**Architecture:** one fresh Python subprocess per call, JSON-only IPC drained
by communicate, one monotonic deadline including startup and trusted checks.
A controlled Solver records formulas at assert_and_track; trusted fresh solvers
derive SAT and deletion-minimal MUS. Generated Python uses one namespace.

**Tech stack:** Python 3.13+, subprocess, Z3, Pydantic, pytest, strict mypy.

## Contract and implementation choices

- Require `solver = Solver()` and exactly one Boolean assertion per input ID.
- Allow expression construction, tracked registration, and read-only check,
  unsat_core, model, assertions, reason_unknown; reject state mutations including
  add, reset, push/pop, set, alternate solver constructors and extra solvers.
- Support `from z3 import Solver`, wildcard imports, and `import z3` through a
  per-worker module facade. Do not patch the trusted z3 module.
- Minimize the entire registered set in sorted ID order, intentionally avoiding
  dependence on Z3's unsat-core heuristic. Validate UNSAT and every removal;
  unknown or deadline at any required check means failure, no partial answer.
- Classify timeout, runtime, contract, unknown, worker crash as execution errors.
- Record protocol `1` only in newly produced Z3 reports; metrics version stays 3.
- Separate process is termination isolation, not a security boundary for Python.

## Tasks (inline execution)

### 1. Reproduce defects

- [x] Add tests in tests/unit/test_sandbox.py and new trusted-solver tests:
  timeout/reaping/recovery, unified namespace, missing solver, forged verdict,
  ID contract, independent minimality, SAT/multiple MUS, unknown, crashes,
  parent interruption, large stdout and large IPC result, import forms.
- [x] Run regressions against the original implementation and record RED.

### 2. Isolated executor and trusted solver

- [x] Replace sandbox/executor.py; add sandbox/worker.py and controlled_solver.py.
- [x] Extend models/evaluation.py and enums.py with diagnostics and protocol.
- [x] Run sandbox tests GREEN; keep strict typing and bounded cleanup.

### 3. Pipeline, reports, documentation

- [x] Pass only input rule IDs from evaluation/strategies/z3.py, update prompt.
- [x] Record protocol in evaluation/pipeline.py, preserving historical nulls.
- [x] Update integration mocks to the required two-argument executor interface;
  replace obsolete child-interrupt propagation test with parent interruption
  coverage (child failures must not abort evaluation under this specification).
- [x] Test continued processing, single-count execution failures, coverage,
  denominator, timing, legacy report reading, semantic errors still scored.
- [x] Document contract, timeout/cleanup, MUS guarantees, protocol and limits.
- [x] Run full pytest, ruff, strict mypy, pylint and project hooks; independent
  final review; commit, push and open PR against master without merge.

## Review focus

Tracking labels colliding with formula symbols; swallowed contract errors;
mutation through alternate APIs; unknown during minimization; startup/transfer
and cleanup delays. Cover each in sandbox tests and review IPC cleanup paths.

## Verification record

- Baseline: full pytest, 215 passed. Original executor accepted bare
  `is_sat=True` and forged SAT over UNSAT; a valid registration function failed
  with `NameError: solver is not defined`. Reproduced before production edits.
- New executor suite: full pytest, 268 passed. Windows native subprocesses,
  independent SMT minimality checks, no LLM or large experiment runs.
- Extra RED/GREEN: a worker not reading a 1 MB request previously outlived its
  deadline and exited normally; file-backed stdin makes it be killed. Unicode
  IPC failed under inherited cp1251; explicit binary UTF-8 fixes it.
- Strict mypy: all 56 source files pass. Ruff check and format: all 81 Python
  files pass. Pylint production/scripts and changed tests: 10.00/10.
- Independent review: no outstanding Critical/Important or Minor findings.
  Reviewer found the Unicode issue above; covered before its fix.
- Static compatibility: master includes PR #1 plotting scripts with missing
  strict annotations and lint issues. Fixed annotations and equivalent lint
  expressions without changing chart parameters, data, or historical artifacts.
- Decisions: optional model-side observations cannot supply final answers;
  only required trusted checks determine success. Deliberate Python internal
  tampering, OS memory/filesystem/network/descendant isolation, minimum-cardinality
  MUS, and semantic translation verification remain outside this protocol.
- Initial pre-commit environment build failed through an unavailable proxy;
  direct network access rebuilt the same locked package successfully. Re-run
  project hooks before committing; no checks or strict settings were disabled.
- Full hook verification: all checks passed and pytest reported 268 passed;
  the manual hook run flagged this plan's concurrent documentation update as
  "files modified". Stage the completed record and let the commit hook verify
  the final unchanged tree again.
