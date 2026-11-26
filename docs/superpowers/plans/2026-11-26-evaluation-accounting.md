# Evaluation accounting implementation plan

**Goal:** implement the user's evaluation accounting specification and regressions A–H on master after PR #2.

**Architecture:** build one finalized `EvaluationCaseReport` per processed case. Validate response eligibility against the input rules (without the reference label), then derive correctness, diagnostics and per-case MUS scores. All metrics consume that same record. Preserve the existing `metric.update(case, prediction, metadata)` interface as a convenience wrapper around the record builder.

**Constraints:** no live LLM requests; no changes to generation, release gates, v1, historical results, article, plots, sandbox isolation, MUS minimization or checkpoints. Work on `codex/fix-evaluation-accounting-and-metrics`; open a PR into master without merging.

## Tasks

- [x] Add and run failing numerical and failure-path regressions (A–H) using mocked completion calls and no retry waits.
- [x] Update `models/evaluation.py`, `evaluation/diagnostics.py`, `evaluation/metrics.py` and `evaluation/pipeline.py`: one case record, validity independent of truth, all-case SAT denominator, per-UNSAT macro metrics, counters, null empty denominators, run reset and explicit completion status.
- [x] Update `extractor.py` and strategies: typed expected extraction failures, raw responses, usage captured before parsing, known/unknown accounting, latency and exhausted transient API errors. Unexpected/configuration exceptions and process interrupts propagate.
- [x] Update `evaluate_llm.py` and README: version reports explicitly, preserve legacy reads, save incomplete progress without claiming completion, document metrics and metadata completeness.
- [x] Review the diff and regression numbers; run full pytest, Ruff, mypy, pylint and applicable repository checks (also enforced on commit).

Delivery: commit, push and open a PR into master, without merge.

## Review focus

- Refusals/errors with an otherwise correct SAT verdict must earn no credit.
- Duplicate and unknown core IDs must not silently change denominators.
- Recovered transient requests have unobserved token costs: retain known usage without claiming complete accounting.
- Empty subsets and interrupted runs must produce honest status and denominators.
- Unversioned historical JSON must not be upgraded to new metric semantics on load.

## Evidence

- Baseline: 154 tests passed (`.venv/Scripts/python.exe -m pytest -q`).
- Base: `d1b2944930f1056a1b69d33269030f3eafebab5c`.
- Initial RED run: 22 regressions failed; A was 0.9412 instead of 0.8, C awarded Exact Match 1.0, schema/network failures escaped, metadata and versions were missing.
- GREEN: A = 0.8 SAT accuracy, 16/17 conditional accuracy, 17/20 coverage; D = 0.5 precision/recall and 4/9 macro-F1.
- Full suite before final review fix: 183 passed; the final accounting suite has 31 passing tests, including strengthened legacy compatibility and missing-verdict coverage.
- Final full-suite check: 185 passed, including all PR #2 release-gate tests.
- Ruff on source/tests and mypy pass; pylint on changed files scores 10/10. Repository-wide Ruff reports 10 pre-existing findings in unchanged scripts.
- Independent review found quadratic CLI report serialization. A regression was observed failing, then passed after preserving initial/final/failure saves and disabling per-case snapshots in CLI. Direct pipeline callers retain optional per-case saves. No additional accounting correctness findings.

## Review follow-up

- Shared completion checks now inspect status, counters and finish metadata in full/smoke/lifecycle runners and analysis. Legacy unversioned files may also be partial: without completed run metadata, completion requires matching dataset/limit or manifest expected counts. Ambiguous old files remain readable but cannot suppress a rerun.
- Schema/metric definitions version 3 separates API, response and execution error categories and rates. Version 2 and unversioned values remain unchanged on read.
- Per-case end-to-end timing includes prompt preparation, requests/retries, validation, Z3 execution and finalization; request timing is retained separately. Historical request timings are never promoted to end-to-end measurements.
- Refusal detection no longer searches arbitrary raw JSON/generated code. Quoted text, inline/fenced code and negated clauses have regression coverage; unrelated negation must not hide a genuine refusal. Explicit provider refusals retain priority.
- Analysis preserves null/NaN, records versions, filters incomplete input and separates versioned comparisons and plots. It does not deduplicate or average different metric definitions together.
- Strict mypy now covers all 52 source/script modules; domain error/status fields use enums and JSON fields have explicit types. Unused ignores were removed, missing-stub ignores narrowed to `import-untyped`, and remaining sandbox/CLI complexity exceptions are documented. Generation/verifier changes are import-annotation comments only.
- Independent follow-up review found legacy partial completion and two additional refusal quoting/negation gaps. Each was reproduced with failing tests before correction; the final targeted regression group passed 64 tests.
