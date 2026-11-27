# Resumable controlled experiment runner

**Goal:** Execute an admitted controlled series with durable case outcomes,
explicit inference conditions, and fail-closed offline resume compatibility.

**Spec:** User's supplied request, regressions A–L. Base: master `2cbd9ca`.

**Architecture:** SQLite EXTRA synchronous rollback journal stores a hash-chained
event history under an OS writer lock. Commit request intent before HTTP, the
response envelope before parsing, and the finalized outcome before the next case.
Existing strategies, build_case_report and metric implementations remain the
evaluation authority. Reports are disposable projections of persisted outcomes.

**Approaches considered:** Atomic per-case files require another attempt index
and recovery protocol. JSONL requires torn-tail repair decisions. SQLite supplies
atomic transactions and crash recovery in the standard library; application
checksums and event validation detect logical corruption. This is an implementation
choice within the requested atomic/journal alternatives.

## Constraints and review focus

- No real HTTP, model loading/downloading, article or historical-result changes.
- Keep generation, leakage threshold, metric definitions and Z3 protocol unchanged.
- Canonical execution uses cell files exactly once; combined is checked, not queued.
- Source identity hashes actual Python bytes, not only the Git commit.
- Unknown model facts and server-unconfirmed settings remain explicitly unknown.
- No exactly-once HTTP claim; unresolved intent requires explicit retry permission.
- Lock ownership must survive stale lock files and release on process death.
- A saved response must survive parser/Z3 failure and never trigger new HTTP.
- A changed series, request, prompt/schema, protocol or source must block resume.
- A failed outcome is final and belongs in all metric denominators.
- Offline commands must work with imports of the network client forbidden.

### Task 1: Offline contract and job inventory

Files: runner/config.py, runner/preflight.py, strategy type-only imports,
tests/integration/test_controlled_runner.py.

- [ ] Write and run failing tests for explicit budgets, secret/unknown-field
  rejection, failed series, exact work counts, and offline import isolation.
- [ ] Implement strict JSON config, expected/user-supplied profile, source/runtime
  fingerprint, full-series release checks and exact per-cell case identities.
- [ ] Verify tests pass and document the inventory and compatibility contract.

### Task 2: Durable journal

Files: runner/journal.py, tests/unit/test_run_journal.py.

- [ ] Write and run failing tests for single writer, atomic rollback, corruption,
  duplicate finalization, incompatible manifest and indeterminate history.
- [ ] Implement OS lock, SQLite transactions, validated checksummed event chain,
  typed replay state and atomic report/manifest snapshots.
- [ ] Verify journal tests, including subprocess termination during transaction.

### Task 3: Capture, replay and existing evaluation integration

Files: response_processing.py, runner/inference.py, runner/execution.py,
evaluation/pipeline.py, models/evaluation.py, extractor.py, enums.py.

- [ ] Write and run failing mocked regressions A–I and L: interrupted/resumed
  equality, error/refusal finality, saved raw replay, truncation, unknown cost,
  context errors, explicit transient retries and mismatch before HTTP.
- [ ] Share response parsing and pipeline case evaluation; add a journal-backed
  extractor that records intent/response/error and replays without HTTP.
- [ ] Build versioned reports exclusively from finalized stored outcomes, with
  run/journal identity and uncertainty counts; no historical guarantee upgrades.
- [ ] Verify all new regressions and existing extractor/pipeline/report tests.

### Task 4: CLI, documentation, review and PR

Files: commands/run_experiment.py, cli.py, README.md,
examples/controlled-run.example.json, docs/resumable-controlled-runner.md.

- [ ] Add offline preflight plus explicit new-run and resume commands.
- [ ] Document crash boundaries, durability assumptions, retry/cost limits,
  recorded settings, provenance and final confirmation dataset limitation.
- [ ] Run full pytest, Ruff, mypy and applicable Pylint checks, inspect diff,
  request independent whole-branch review and fix material findings.
- [ ] Commit, push requested branch and open PR against master without merge.

## Review decisions

Independent review exposed LiteLLM's hidden request rewriting/retries and usage
zero-filling. The controlled runner now uses a single stdlib urllib JSON POST,
without redirects, environment proxies or implicit retries. New boundary mocks
prove unchanged payloads, one HTTP call per attempt and unknown usage preservation.
The selected manifest is now the authoritative admission gate; a copied rejected
manifest cannot borrow admission through absolute paths. A committed tail anchor
detects event deletion; unknown usage contributes to unknown-cost diagnostics.
All material findings have dedicated regression tests.
