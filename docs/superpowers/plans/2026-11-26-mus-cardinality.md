# Exact MUS Cardinality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

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

- [ ] Write parameterized real-Z3 regressions for exact K, unique MUS, fixed patterns, invalid input and tight N. Update old tests that explicitly encoded K+1.
- [ ] Run the new tests; expect cardinality/eligibility failures on baseline.
- [ ] Correct topology budgets/eligibility and generator validation; introduce v2 generation filenames with v1 evaluation fallback.
- [ ] Run generation/integration/CLI tests; expect PASS. Commit.

### Task 2: Pair-preserving presentation and prompt hygiene

**Files:** models/rules.py, generation_rendering.py (new), generator.py, evaluation/strategies/*.py, tests/unit/test_presentation.py (new).

**Interfaces:** sign/inequality transformations preserve semantics and use label-independent seeded randomness; prompt builders contain no case identifiers or UUIDs.

- [ ] Write regressions for prompt independence from case identity, alias randomization, signed AND/OR semantics, text/formula agreement and deterministic pair generation.
- [ ] Run tests; expect identity leak and missing signed-semantics failures.
- [ ] Implement transformations and shared renderer; remove CASE_ID/UUID; ensure numeric variables are declared with numeric types.
- [ ] Run the full suite; expect PASS. Commit.

### Task 3: Honest leakage audit and release gate

**Files:** leakage.py (new), models/manifests.py, models/pipeline.py, run_pipeline.py, commands/generate.py, hashing.py, README.md, scripts/audit_generation.py (new), tests/unit/test_leakage.py (new), tests/integration/test_generation_release.py (new).

**Interfaces:** TfidfMetrics retains old F1 fields and adds nullable balanced accuracy, fold scores/status. LeakageReport exposes acceptance at a configurable limit; run_generation saves diagnostics and raises on failed/unavailable audit.

- [ ] Test identical paired texts (balanced accuracy 0.5), known lexical leak, unavailable/invalid CV, pair grouping, threshold boundaries and persisted rejection.
- [ ] Run tests; expect missing functionality failures.
- [ ] Move diagnostics to focused module; calculate global/per-K metrics, validate logical release conditions, repair source bundle hash for new artifacts, expose --leakage-threshold.
- [ ] Run full pytest, Ruff, typing and a small predeclared multi-seed offline audit. Expect tests/checks PASS; report every audit result honestly rather than requiring every seed to pass.
- [ ] Update README and ledger, commit, obtain fresh whole-branch review, resolve important findings with regression tests, open PR against master.
