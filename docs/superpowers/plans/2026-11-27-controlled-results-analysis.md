# Controlled results analysis

Implement the supplied A–L specification on master at 756c7ab, on
`codex/controlled-results-analysis`; open a PR without merging. No model calls.

## Design and decisions

One offline analysis package owns loading, compatibility, aggregation, intervals and
contrasts. Reuse normalized PR #3 outcomes and metric classes. Strengthen the shared
report verifier with read-only journal access and saved inventory/state checks; never
require historical datasets or today's source hash. Reject unknown metric semantics.
Separate plotting reads the exported tables and performs no outcome interpretation.
Extending legacy plotting would retain unsafe identity assumptions; independent metric
implementations would drift. Neither is used for controlled data.

The strict JSON plan selects run UUIDs into named groups and records purpose, metrics,
contrasts and seeded pointwise interval settings. Keep all recorded dimensions and
model IDs. No implicit pooling. Conflicting repeated observations require selecting
separate groups/runs. Diagnostic mode describes incomplete runs without estimating a
complete experiment; legacy mode preserves supplied fields without granting provenance.
Strategy-specific requests may differ between direct and Z3; within a strategy saved
requests for the same case must agree, and execution/inference conditions must match.

## Implementation sequence

1. Reproduce legacy case/pattern collisions, F1 and de-duplication errors on tiny
   fixtures; add offline regression tests for the new API and numerical methods.
2. Add strict plan types, saved read-only verification, run/group selection and
   compatibility diagnostics. Test stale/corrupt/incomplete reports and source hashes.
3. Export case and summary tables using existing metric classes; add Wilson and
   deterministic family cluster bootstrap, strict paired strategy/noise contrasts.
4. Add table-only plots, legacy refusal guards, development example and README/docs.
5. Run A–L regressions and full existing suite, ruff, mypy, pylint; visually inspect
   small synthetic figures, review the final diff, commit, push and open the PR.

## Review focus

- Root/subgroup/duplicate inputs: validate every supplied report, count each job once.
- Missing pairs: retain explicit missing IDs and reject primary contrast.
- Related N variants: sample entire sorted families with identical draws on both sides.
- Unknown costs/replay latency: preserve null and report accounting completeness.
- Purpose/diagnostic separation: select explicitly and reject primary contamination.

The development example is not the paper's final confirmation plan. No p-values,
equivalence claims, generator/metric/Z3 changes or edits to historical results.

## Execution record

All five implementation steps completed. Ruling: cross-cell weighted estimates are
not implemented; reject implicit aggregation and require a reviewed weighted method
before adding one. This avoids selecting scientific weights during implementation.
Ruling: retain the clean existing checkout on the user-named feature branch; no
additional worktree is needed for this already isolated task branch.

Legacy collisions reproduced before the guards. Numerical/API regressions observed
failing before implementation, including reviewer-found contradictory report versions
and empty selectors. Read-only independent review completed; its fixes were checked.
Full final suite: 406 passed. Ruff check/format, strict mypy and Pylint passed.
Fourteen mock-only figures were generated and visually inspected; no real LLM calls.
Publication step remains the explicitly requested PR against master, without merge.
