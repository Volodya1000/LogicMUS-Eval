# Confirmation Release Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare a versioned, reproducible, honestly blocked confirmation release and PR.

**Architecture:** Reuse preparation gates, RunConfig/preflight/journal and AnalysisPlan.
Add only offline release inventory/integrity/evidence, prospective validation and
technical binding, plus runner initialization before HTTP.

**Tech Stack:** Python 3.13, existing Pydantic/Typer/Z3/pytest; no dependencies added.

**Spec:** docs/superpowers/specs/2026-11-28-confirmation-release-design.md and supplied task.

## Global Constraints

No real HTTP/model loading; one fixed preparation; preserve failures and threshold.
No metric/statistic/generator/Z3 semantic changes; preserve historical artifacts.
All unknown facts block launch; no GitHub Release/tag or external archive upload.

## Review Focus

- Repeated families never multiply independent sample size.
- No partial/ambiguous contrasts or dropped pairs before HTTP.
- A changed config/profile/budget/analysis/dataset invalidates the freeze.
- Copied bundles validate with relative paths and exact hashes.
- Empty initialization and fabricated smoke must not yield launch readiness.

### Task 1: Inventory and prospective analysis

Files: create logicmus_eval/confirmation/{inventory,prospective}.py and tests/integration/test_confirmation_release.py.
Consumes ExperimentPlan, RunConfig, AnalysisPlan. Produces inventory(plan, configs), validate_template(plan, configs, template).
- [ ] Write failing tests for counts, family reuse, complete contrasts and invalid selectors.
- [ ] Run tests and observe missing implementation.
- [ ] Implement strict inventory and pre-HTTP prospective validation using existing identities.
- [ ] Run targeted tests; commit.

### Task 2: Offline initialization and immutable binding

Files: modify runner/execution.py, commands/run_experiment.py, cli.py; create confirmation/binding.py.
Produces initialize_run(config, root), bind_release(root, runs_root), resume_bound(...).
- [ ] Write failing tests for zero HTTP initialization, UUID-only binding, no initialization twice, and rejection before HTTP.
- [ ] Implement initialization by extracting new_run's existing setup; preserve execution behavior.
- [ ] Bind exact initialized inventories before any attempts; verify binding on gated resume.
- [ ] Run runner and binding tests; commit.

### Task 3: Freeze, evidence and verification

Files: create confirmation/{models,service}.py, commands/confirmation.py; update cli.py.
Produces freeze_release(root), verify_release(root), seal_preparation(root).
- [ ] Write failing tests for tampering, unknowns, failed gates, missing/fake smoke, offline operation and mock end-to-end analysis.
- [ ] Implement explicit statuses, source/environment hashes, all-artifact inventory and verified smoke receipts.
- [ ] Run new tests and PR 5–7 integration regressions; commit.

### Task 4: Frozen release and one preparation

Files: releases/confirmation-v1/*, docs/confirmation-release.md, README.md.
- [ ] Create fixed plans/profiles, logical analysis, protocol and pre-preparation inventory.
- [ ] Freeze seeds/size, print counts, then execute prepare-experiment exactly once.
- [ ] Preserve every result, seal artifacts, report measured gates and unexplained leakage honestly.
- [ ] Produce local archive, hash inventory and copy/reproduction instructions.
- [ ] Run full project checks and independent code review; fix substantive findings.
- [ ] Commit, push codex/freeze-confirmation-release, create PR into master without merge.
