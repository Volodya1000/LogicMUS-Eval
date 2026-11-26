# Exact MUS Cardinality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make the generator's K scientifically meaningful and measure/reduce lexical artifacts honestly.

**Architecture:** Explicit topology contracts determine variable and rule budgets. Pair-preserving symmetries randomize presentation. A dedicated leakage module reports grouped CV and gates generation.

**Tech Stack:** Python 3.13, Pydantic, Z3, scikit-learn, pytest.

**Spec:** docs/superpowers/specs/2026-11-26-mus-cardinality-design.md

## Global Constraints

- No article edits or model inference; published v1 artifacts remain immutable.
- K is the exact cardinality of the unique expected UNSAT MUS.
- Default leakage balanced-accuracy limit 0.55, chance level 0.5.
- No seed retries/selection to pass the probe. Missing diagnostics cannot pass.

## Review Focus

- K/N boundaries and fixed-topology eligibility must not overrun a budget.
- Text must represent transformed symbolic constraints, including signed OR/AND.
- Paired samples must never cross CV folds; failures must remain visible.
- New filenames must not overwrite frozen v1 and legacy evaluation must work.
- Small samples and rejected leakage checks must produce honest status/artifacts.

### Task 1: Exact topology and generation contracts

**Files:** patterns/*.py, generator.py, enums.py, commands/generate.py, run_pipeline.py, tests/unit/test_generator.py, tests/integration/test_pipeline.py, tests/unit/test_generation_contract.py.

**Interfaces:** strategies expose supports(K), core_variable_count(K), core_rule_count(K). Generator emits exact-N pairs with metadata pattern_id/pair_id/generator_version.

- [x] Write parameterized real-Z3 regressions for exact K, unique MUS, fixed patterns, invalid input and tight N. Update old tests that explicitly encoded K+1.
- [x] Run the new tests; expect cardinality/eligibility failures on baseline.
- [x] Correct topology budgets/eligibility and generator validation; introduce v2 generation filenames with v1 evaluation fallback.
- [x] Run generation/integration/CLI tests; expect PASS. Commit.

### Task 2: Pair-preserving presentation and prompt hygiene

**Files:** models/rules.py, generation_rendering.py (new), generator.py, evaluation/strategies/*.py, tests/unit/test_presentation.py (new).

**Interfaces:** sign/inequality transformations preserve semantics and use label-independent seeded randomness; prompt builders contain no case identifiers or UUIDs.

- [x] Write regressions for prompt independence from case identity, alias randomization, signed AND/OR semantics, text/formula agreement and deterministic pair generation.
- [x] Run tests; expect identity leak and missing signed-semantics failures.
- [x] Implement transformations and shared renderer; remove CASE_ID/UUID; ensure numeric variables are declared with numeric types.
- [x] Run the full suite; expect PASS. Commit.

### Task 3: Honest leakage audit and release gate

**Files:** leakage.py (new), models/manifests.py, models/pipeline.py, run_pipeline.py, commands/generate.py, hashing.py, README.md, scripts/audit_generation.py (new), tests/unit/test_leakage.py (new), tests/integration/test_generation_release.py (new).

**Interfaces:** TfidfMetrics retains old F1 fields and adds nullable balanced accuracy, fold scores/status. LeakageReport exposes acceptance at a configurable limit; run_generation saves diagnostics and raises on failed/unavailable audit.

- [x] Test identical paired texts (balanced accuracy 0.5), known lexical leak, unavailable/invalid CV, pair grouping, threshold boundaries and persisted rejection.
- [x] Run tests; expect missing functionality failures.
- [x] Move diagnostics to focused module; calculate global/per-K metrics, validate logical release conditions, repair source bundle hash for new artifacts, expose --leakage-threshold.
- [x] Run full pytest, Ruff, typing and a small predeclared multi-seed offline audit. Expect tests/checks PASS; report every audit result honestly rather than requiring every seed to pass.
- [x] Update README and ledger, commit, obtain fresh whole-branch review, resolve important findings with regression tests, prepare PR against master.

## Final verification and review

- Full suite: 154 passed. Ruff and formatting pass for package/tests/audit/smoke;
  mypy passes all 45 package modules; pylint package passes; git diff --check clean.
- A fresh reviewer inspected 2147637. Important findings were reproduced with
  failing tests and fixed in one pass: signed operand scope and role aliases,
  smoke filename, predicate-budget eligibility, renamed-v2 approval, and missing
  or non-finite audit measurements. Each fix is covered by regression tests.
- Regraded deterministic legacy filename selection and cached rejected-data
  reuse as important compatibility/release conditions; both fixed. Full-grid
  model loading is also blocked when there are no approved datasets.
- Probe direct and Z3 inputs separately: extra declaration text can dilute a
  lexical classifier, so the combined view alone was insufficient.
- Pre-commit environment bootstrap was unavailable through the configured package
  proxy. Installed pytest/Ruff/mypy/pylint and diff checks were run directly.
  Git's unavailable proxy is overridden per network command only, not persistently.
- Four pre-existing full-grid Ruff warnings (TRY004, DTZ005, two BLE001) remain;
  they are outside these changes. Package/tests/new audit/smoke lint is clean.
- Legacy generic uniqueness, sandbox, evaluation denominator/aggregation,
  historical plots, broad natural-language validity and paper conclusions remain
  separate follow-up work. No claim that those were fixed by this PR.
- Development audit: fixed seeds 7,42,2026; 25 pairs/K has failures retained.
  Additional post-hoc 100-pair/K calibration passes every <=0.55 check; global
  balanced accuracy 0.4925..0.5125. Both complete audits are committed under
  docs/validation/generation-audit-2026-11-26.json. No LLM inference.

- [ ] Open pull request against master (publication step).
