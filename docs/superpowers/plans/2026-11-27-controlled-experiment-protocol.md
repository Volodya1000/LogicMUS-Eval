# Controlled experiment protocol implementation plan

**Goal:** Offline, reproducible comparable task series for future experiments.

**Architecture:** Keep legacy v2 generation unchanged. Add strict JSON plans,
domain-separated construction/noise/presentation, family-grouped audits and a
fail-closed series manifest. Use the existing Pydantic, sklearn and Z3 dependencies.

**Spec:** User's supplied controlled-experiment request, including regressions A–J.

## Global constraints

- No LLM endpoints, model downloads, article edits, historical artifact changes,
  sandbox rewrites, metric changes, seed search or threshold/sample-size relaxation.
- Branch `codex/controlled-experiment-protocol`, base master `d1e8b81`, PR without merge.
- Protocol `controlled-v1`; old generation remains v2, published v1 untouched.
- Stable family identity excludes N and sample purpose. Reserve even seeds for
  development and odd seeds for confirmation, explicitly validated before generation.
  This prevents related families crossing purpose boundaries across separate plans.
- Noise sweep fixes one pattern and K; K sweep fixes one scalable pattern and N;
  topology panel specifies supported cells individually and never substitutes patterns.

## Review focus

Invalid late cells must fail before writes; failed cells must remain in manifests;
renamed controlled datasets must still require release approval; added N values must
not affect aliases/text/order; historical reports must retain unknown provenance.

### Task 1: General prompt semantics and report provenance

Files: shared prompt semantics, direct/Z3 templates, evaluation model/diagnostics,
tests/unit/test_protocol_reporting.py.

- [ ] Reproduce FACT/terminal-only instructions and lost provenance with failing tests.
- [ ] Share material implication, inclusive OR, open-world and mixed numeric/Boolean
  semantics. Keep existing JSON formats and ID/Var/type support.
- [ ] Optional typed experiment provenance in reports; no inference for old data.
- [ ] Test coverage/idem/merge/math requests, metadata isolation and report round trips.

### Task 2: Typed plans and controlled generation

Files: experiment_plan.py, controlled_generation.py, tests/unit/test_controlled_generation.py.

- [ ] Add failing regressions for current same-seed N drift and new A–F contracts.
- [ ] Validate all patterns/K/N/predicate capacities before generating anything.
- [ ] Canonical plan/cell/family/pair/case identities, independent random streams,
  stable rule correspondence and insertion order. Reject unsupported cells.
- [ ] Verify exact counts, pair edits, nested noise, reorder/extension invariance,
  split separation, fork construction count, full-pool boundary.

### Task 3: Offline preparation and release gate

Files: experiment_preparation.py, independent_smt.py, prepare command, release.py,
leakage.py, tests/integration/test_experiment_preparation.py.

- [ ] Write failing tests for family CV grouping, failed audit blocking and deterministic artifacts.
- [ ] Save every planned cell, per-case SMT/unique MUS diagnostics, independent
  serialization-to-SMT control, cell and combined family-held-out leakage diagnostics.
- [ ] Final manifest contains normalized plan/hash, source provenance, dataset hashes,
  all diagnostics and readiness; gate verifies complete series and all file hashes.
- [ ] CLI exits unsuccessfully on failed mandatory checks, preserving artifacts.

### Task 4: Documentation, development example, verification and PR

- [ ] Document inference boundaries and synthetic template requirements with structural annotations.
- [ ] Run tiny development preparation twice; preserve failure diagnostics without tuning.
- [ ] Run full suite, formatting, type/lint checks; review whole diff.
- [ ] Commit, push authorized branch and open PR in master without merge.

## Execution record

Base confirmed from origin. Working in the clean user checkout on the dedicated
requested branch; no additional worktree needed. Detailed specification supplies
authorization to implement routine design decisions without another approval gate.

Implementation and review are complete. Baseline: 268 passing tests. Final full
suite: 330 passing tests; Ruff check/format, strict mypy and pylint pass. Seven
review findings were reproduced, fixed and re-reviewed; all 28 focused review
regressions passed. The complete controlled generator/preparation regression
selection passed 50 tests before the final full suite.

Development preparation retained all 9 cells (72 cases). Both SMT paths pass
all cells; 6 cell leakage audits pass and 3 fail, and the combined audit fails.
The series is not ready for evaluation. Seeds [42, 44], two pairs per seed and
threshold 0.55 were never tuned. Two separate preparations produce identical
scientific artifacts. Initial failed diagnostics remain in separate local data
directories; reviewed/final artifacts are not presented as confirmation data.

Additional review decisions: use a common literal wording pool only in the new
mode; compare actual saved JSONL with oracle input and check saved formulas
independently; bind stored evidence to every planned case; enforce family-held-out
fold counts; retain ordinary cell errors without catching interrupts. These
decisions implement release requirements rather than weakening acceptance.
