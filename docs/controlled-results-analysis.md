# Offline controlled results analysis

This is a development analysis implementation, not the final paper plan or a new
confirmation experiment. It makes no endpoint calls, imports no network client,
and does not generate cases, resume a run, re-execute Z3, or edit saved sources.

```powershell
# Replace the example UUID and full served model identifier from run.manifest.json.
# Freeze the plan before looking at the selected results.
uv run --group analysis logicmus-eval analyze-controlled --run experiments/run-01 --plan examples/controlled-analysis.development.json --output experiments/analysis-dev-01

# Repeat --run to select multiple saved runs/reports. A parent directory discovers
# its saved runner directories; the plan must explicitly select exactly those UUIDs.
uv run --group analysis logicmus-eval analyze-controlled --run experiments/run-01 --run experiments/run-02 --plan analysis-plan.json --output experiments/analysis-dev-02 --no-plots

# Already installed dependencies: avoid package-manager synchronization entirely.
python -m logicmus_eval.cli analyze-controlled --run experiments/run-01 --plan analysis-plan.json --output experiments/analysis-dev-03 --no-plots
```

The output directory must be fresh and separate from saved runs. Supplying a root
and its subgroup reports counts each run/job once; every explicitly supplied report
is checked, so a stale subgroup cannot hide behind a current root. Exact copies
of one run UUID do not increase the sample. Conflicting snapshots are rejected.
Distinct runs are retained by UUID, regardless of display names. If two runs repeat
the same case/model/strategy, select one explicitly or put them in separate named
groups; there is no `keep=first` substitution. A subgroup input resolves to the full
verified root; use group `model_ids`, `strategies`, and `cell_ids` to narrow it.

## Authority and compatibility

`verify_runner_report` compares the report with its manifest, inventory, committed
journal head, event chain, state transitions, normalized finalized outcomes and
reconstructed PR #3 metrics. Analysis opens the existing lock and SQLite database
in read-only mode and refuses a concurrent writer. It uses the saved executable
identity, not today's source bundle, Git HEAD, external config or dataset path.
Historical source/data directories need not still exist. Saved identity hashes
detect corruption, not an adversary rewriting both evidence and checksums.

Compatibility checks include experimental provenance, runner/transport/report/metric
versions, saved source bundle and runtime, endpoint/retry/timeouts, full model ID,
supplied model profile, generation settings and response schemas. Prompt contents
are compared for repeated case/model/strategy keys. The source bundle conservatively
identifies prompt implementations across different cases. This can reject runs after
unrelated source edits; the implementation provides no unreviewed compatibility
override. Z3 protocol/timeout are compared only for Z3. Prompt/schema signatures are
scoped by full model ID and strategy, so planned direct versus Z3 comparisons are
allowed despite their different prompts and schemas. Observed profile contradictions
are rejected; unknown model facts and applied backend settings remain unverified.

`purpose` must match saved provenance. Primary analysis requires all root jobs to be
finalized, including errors/refusals. Diagnostic reruns are rejected in primary mode.
`mode: "diagnostic"` exports verified finalized cases and missing job IDs/counts but
leaves summary/contrast tables empty. This is not a completed experiment. Development
and confirmation cannot be pooled. Admission and model verification remain upstream
requirements; offline analysis is not a server attestation.

## Plan and tables

The strict Pydantic JSON plan forbids unknown fields. It records the analysis version,
purpose/mode, named groups with explicit saved run UUIDs, optional exact model/strategy/
cell selections, primary MUS Exact Match, additional metrics, contrasts, and interval
method/level/repetitions/seed/minimum families. The seed is mandatory; defaults are
10,000 repetitions, 95% pointwise intervals and at least two independent families.
The example's placeholder UUID/model and illustrative contrast must be replaced with
prospective selections matching actual saved inventory; it is not a ready article plan.

Outputs:

- `cases.csv`: run/job/case/cell/family/pair/pattern/series identities, purpose, K/N,
  full model ID and strategy, normalized correctness/validity/MUS scores, primary
  errors, exclusive error bucket and original nullable usage/latency metadata.
- `summary.csv`: separate rows by group, purpose, series ID/kind, pattern, K, N,
  full model ID and strategy; planned/processed/UNSAT/family counts, PR #3 metrics,
  measurement coverage, exclusive outcome composition, and named interval columns.
- `contrasts.csv`: planned right-minus-left differences, pair/family counts,
  interval status/reason/bounds, method, scope and degeneracy flag.
- `diagnostics.json`: completion/missing jobs, saved runner diagnostics, compatibility
  fingerprints/unknowns, missing paired observation IDs, and rejection reasons.
- `analysis.manifest.json`: full normalized plan and hash, analyzer source identity,
  exact input hashes, saved manifest/identity/journal head and event count, method
  settings, table hashes and completion/rejection status. Even a rejected analysis
  preserves its plan and diagnostic reason. Do not plot a rejected manifest.

No implicit model, pattern, K or N averaging is supported. Contrasts must select one
cell per side. A proposed cross-cell estimand needs explicit scientific weights and
a corresponding reviewed method; this version rejects such requests instead of
silently choosing weights. Repeated families across N retain their identity.
An absent cell has no summary row; no metric is filled with zero. An empty denominator
remains null. Usage is summed only where observed, and coverage plus
`token_accounting_complete` expose omissions/retries. Missing usage and interrupted
case/LLM latency stay null; replay time is never substituted.

## Estimands and intervals

PR #3 metric classes consume saved normalized outcomes. Invalid responses, refusal,
execution failure and truncation remain in their original denominators. MUS metrics
use **all reference UNSAT cases**, regardless of predicted SAT or Z3 success. Macro-F1
is the mean of per-case F1, not F1 reconstructed from average precision and recall.

The independent resampling unit is `family_id`. SAT/UNSAT pairs and related N variants
travel together. Within a cell, MUS Exact Match uses Wilson only after verifying
exactly one UNSAT row per family. If this condition fails the Wilson interval is
unavailable with a reason; the row count is never passed as an independence count.
Macro-F1, coverage and SAT accuracy use percentile cluster bootstrap. Families and
within-family values are sorted before seeded resampling, independent of input order.
Whole-family contributions retain their multiplicity and size. With fewer than two
families intervals are unavailable. A degenerate bootstrap is explicitly marked:
`[0,0]` does not establish equivalence, and `[1,1]` does not establish population
perfection. Wilson remains nondegenerate at zero/all observed successes.

Strategy contrasts join exactly the same `case_uid`, model, references and fixed
dimensions, with direct and Z3 on opposite sides. Noise contrasts require the same
families, reference SAT status, series/pattern/K/model/strategy inside `noise_sweep`,
with different N. Every expected eligible observation on both sides must be present.
Missing sides reject the primary contrast and list IDs in diagnostics; no convenient
intersection is used. Family draws are identical for both sides because paired
differences are resampled as whole clusters. K changes do not define pairs; matching
seed/index is insufficient, and K-sweep contrasts are not implemented.

These are **pointwise**, not simultaneous intervals. No p-values, automatic superiority
claims, equivalence tests, multiplicity correction or population generalization from
the development examples are supplied.

## Figures and legacy data

Plotting reads hash-checked `summary.csv`/`contrasts.csv` only, with no separate metric
implementation. Outputs cover quality versus N (`noise_sweep`), quality versus K
(`k_sweep`, whose admitted scalable families are chain/math), topology panels with
actual K labels, coverage/exclusive errors and paired differences. Series, patterns,
models and fixed budgets remain separate panels. Sparse points are not joined across
missing cells. Axis labels name metrics, interval scope, level and method; unavailable
intervals have no fabricated bar, and degenerate contrasts are labeled.

The 100% composition uses this mutually exclusive priority: refusal; recorded primary
error type; invalid/unknown response; wrong SAT verdict; wrong MUS; correct. Every case
appears once. Empty or unknown diagnostic tags do not imply correctness. Coverage uses
the PR #3 `valid_response` field, so it includes valid but incorrect answers.

Legacy consumers reject controlled run directories, analysis tables and controlled
reports referenced from legacy manifests, pointing to `analyze-controlled`. Historical
files remain readable by old readers. Explicit `mode: "legacy"` takes JSON/CSV files,
exports their supplied fields in `legacy.csv` with `provenance_status: "legacy"`, and
computes no statistical intervals or pairings. It does not invent missing pattern,
family, versions or provenance. Legacy plan groups can use a descriptive placeholder
ID; they do not attest runner UUIDs. Stored legacy scores are descriptive, not validated
controlled metrics.

## Offline regressions and remaining pre-run work

Small reproductions confirmed the old local-ID/template-pack collision and distinct
run loss through `keep=first`. New A–L regressions cover these identity boundaries,
root/subgroup duplicates, stale/tampered/incomplete sources, compatibility beyond
metric versions, error/refusal denominators, missing pairs, deterministic whole-family
bootstrap, purpose/diagnostic separation, null measurements and offline imports.
Numerical reference checks include:

- Wilson 7/10: approximately `[0.3968, 0.8922]`.
- `(P,R,F1) = (1,1/2,2/3), (1/2,1,2/3), (0,0,0)`:
  macro P = R = 1/2, macro F1 = 4/9.
- One correct plus four UNSAT failure/wrong-answer outcomes: EM = F1 = SAT accuracy
  = 1/5; validity coverage = 2/5.
- Unequal clusters `a=[0,0,0]`, `b=[1]`: exact bootstrap support is
  `{0, 1/4, 1}`, not a row-bootstrap distribution.

Before a large run: freeze/admit the final confirmation sample, fix the prospective
analysis plan and contrasts/weights, justify adequate independent family counts,
verify actually loaded model revisions/tokenizers/templates and backend-applied
settings, and preserve complete quiescent runner directories. This PR performs no
real LLM calls or large experiments and changes no article or historical results.

Validation on 2026-11-27 (Python 3.13.9): `python -m pytest -q --tb=short`:
**406 passed**; `ruff check .`, `ruff format --check .`, `mypy`, and Pylint over
the package, changed legacy consumers and new tests passed. A mock-only 72-outcome,
18-cell demonstration generated 14 figures. Noise/K/topology, coverage/errors and
paired-difference figures were visually inspected, including actual topology K labels
and degeneracy marks. The independent known noise F1 contrast was -0.4 with
interval [-0.8, 0]. A second read-only review confirmed the version/selection fixes
and found no remaining substantive issues. Demonstration outcomes are artificial;
they are not measurements of any real model.
