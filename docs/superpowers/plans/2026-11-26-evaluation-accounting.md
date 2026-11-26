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
