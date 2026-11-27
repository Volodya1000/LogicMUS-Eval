# Analysis hardening implementation plan

Goal: harden existing PR #7 on its current branch without changing scientific
estimands, statistical algorithms, metric definitions, CLI or CSV columns.

Architecture: validate saved JSON once into Pydantic boundary models, carry typed
dataclasses internally, and serialize only at artifact boundaries. Acquire the
existing runner lock once per snapshot; verification, reads and hashes share it.
Publish a running manifest before plotting, then atomically publish complete or
rejected state with hashes for every retained artifact. Metric classes, intervals
and contrasts share the same per-outcome semantic functions.

- [x] Reproduce premature completion and unlocked report reads with regressions.
- [x] Introduce validated saved-run contracts and typed analysis rows/results,
      conditions/diagnostics/manifest; remove Any from analysis and added replay API.
- [x] Split selection, legacy, artifacts and service from the package public API.
- [x] Reuse metric observation semantics in aggregation, bootstrap and contrasts.
- [x] Verify success/failure publication and coherent read-only snapshots, preserve
      numerical regressions and exact old CSV schemas, and inspect generated plots.
- [x] Run full pytest/Ruff/strict mypy/Pylint/pre-commit and independent review;
      prepare the existing branch and PR #7 description for publication.

Delivery rule: push only the existing branch and update PR #7; no new PR, merge
or real LLM requests. Publication is tracked by the PR head and description.

Review focus: partial figures after exceptions, interruption versus completion,
manifest atomicity, hashes of exactly parsed bytes, root/subgroup lock scope,
nullable/zero metric contributions, finite schema types versus dynamic JSON leaves.


Execution evidence: original defects and review-found edge cases were reproduced
before fixes. Internal domain contracts have no Any; a fixed TypedDict preserves the
interval dictionary API. The existing live mutable trace serializer is retained as
an adapter, not used for offline computation. CSV columns/values were independently
compared against original PR commit 8a08c66 (72 cases, 18 summaries, 2 contrasts),
and regenerated figures were visually checked. Wilson/bootstrap formulas are unchanged.

Environment ruling: pre-commit dependency synchronization attempted an unnecessary
editable rebuild through an unavailable proxy. Use UV_NO_SYNC=1 with the already
installed locked dependencies; all validation hooks still execute. No hook is skipped.
Publication is recorded by the existing PR's head/description, not a new PR or merge.

Final validation: 418 tests collected and the complete pytest hook passed; all
pre-commit hooks over every PR file passed with UV_NO_SYNC=1. Ruff check/format,
strict mypy with typed Pydantic constructors and the negative type-contract test,
and Pylint passed. Review-found uncommitted-redraw and partial-table cases were
reproduced before their fixes, as was mixed available/unavailable CSV interval data.
No new scientific method or interpretation is introduced.
