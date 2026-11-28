# Confirmation protocol v1 — frozen before preparation and inference

Scope: synthetic template requirements with structural ID/Var/Bool/Real
annotations. Conclusions concern these templates and the selected models,
strategies and conditions. No claims about unrestricted natural language,
agents, other formalization formats or benchmark families.

## Questions and grid

1. How does independent distracting noise change MUS Exact Match within chain
   and math, preserving each underlying conflict and existing rule order?
2. How does MUS size relate to performance separately within chain and math
   at fixed total N? K changes the family and this is not a paired comparison.
3. How do all seven supported topologies perform at the stated pattern/K/N?
   This panel varies topology and supported K jointly; it does not isolate K.
4. How does z3 translation compare with direct reasoning within each model/cell?

| Series | Patterns | K | N | Cells |
|---|---|---|---|---:|
| noise-chain | chain | 4 | 8,16,32 | 3 |
| noise-math | math | 4 | 8,16,32 | 3 |
| size-chain | chain | 3,4,6 | 16 | 3 |
| size-math | math | 2,4,6 | 16 | 3 |
| topologies | direct; chain; math; coverage; idem; fork; merge | 2;4;4;3;3;3;4 | 16 | 7 |

Three N points distinguish baseline, intermediate and high distraction without
an exhaustive grid. Three supported K points characterize each scalable family.
N=16 links the series. Every topology has its own cell. For fork the construction
has 4 rules and K=3, so independent noise is N−4, not N−K. Stable insertion and
all existing SMT, minimality, uniqueness, saved-artifact and family guarantees
remain unchanged. No model answers influence this grid.

## Sample size and precision

Seeds **2718281 and 3141593**, **128 pairs per seed**, chosen before any
preparation: **256 independent UNSAT families per cell**, each with a SAT mate.
These are odd confirmation seeds; development uses even seeds. The checked
development reference and fixed smoke plan are included in the release.

For one binary MUS Exact Match observation per independent UNSAT family, use
the existing 95% Wilson interval. Its worst-case half-width at p=0.5 is
z/(2 sqrt(n+z²)), z=1.959964: n=256 gives **6.0794 pp**, n=512 gives **4.3148 pp**.
Recommend **256**, a precision/cost compromise that avoids doubling the full
inference workload for about 1.8 pp tighter marginal intervals. This is a
precision calculation, not power for a paired effect or an equivalence design.
`min_families=2` is a software guard, not a scientific sample-size justification.

For paired binary outcomes D=right−left, var(D)=q−delta², where q is the
discordant-response probability and delta=E[D]. Approximate sampling SE is
sqrt((q−delta²)/256). At delta=0 it ranges from zero to 6.25 pp; q=0.1 gives
1.98 pp and q=0.5 gives 4.42 pp. These are illustrative assumptions, not measured
discordance or promised power. No claim of detecting a small effect is made.

The 19 cells contain 4,864 family/cell occurrences and 9,728 cases, but only
**2,816 distinct family_id**: chain K=3,4,6; math K=2,4,6; and five fixed
topologies, 256 each. Chain/math K=4 each reappear in five cells (three noise
N variants, one K-sweep cell, one panel cell). SAT/UNSAT and these repetitions
remain one independent family. Three models and two strategies add observations,
not independent families. Cross-series copies are retained as explicit cells;
the combined file is never submitted as extra jobs.

## Models and requested conditions

Preserve the three models from `scripts/run_full_grid.py`: Qwen2.5-Coder-14B,
Gemma-4-E4B and GPT-OSS-20B. The old LiteLLM names are historical repository
facts; candidate HTTP request IDs come from the old load keys and are not
claimed observed served IDs. `model-facts.json` distinguishes repository facts,
operator input, observations and unknowns. No model selection by expected or
observed accuracy. Model revisions/files, quantization, active context, backend
version, tokenizer and chat template remain unknown until documented.

Each existing RunConfig proposes both strategies, max_tokens=2048,
temperature=0, top_p=1, no requested generation seed or reasoning effort,
request timeout=120s, Z3 timeout=5s. HTTP transport retains existing schema,
redirect/proxy rules and no implicit retries. These are requested settings;
they do not demonstrate the backend applied them.

**Before confirmation inference**, on the fixed development smoke tasks:
verify supported parameter mapping and chat/schema overhead using the actual
tokenizer/template; count every planned prompt and require max input plus
output cap <= active context. Development stress N=48 must cover the maximum
confirmation input in tokens for each model/strategy. If it does not, stop and
define a new release/smoke version before inference. Measure truncation and
transport timeouts. The proposed 2048/120 settings are accepted only if the
development check has no output-cap truncation or request timeout. Otherwise
retain results, choose a new cap equal to the next power of two above the
observed requirement (or a separately justified measured bound if all outputs
are truncated), and a timeout >= twice the largest observed successful request
latency. Freeze this as a **new release version** and repeat development
validation. Do not tune to correctness, change models, discard wrong answers,
or raise budgets/timeouts after confirmation failures. Unobserved or unsupported
backend defaults for omitted parameters must be recorded by the operator.

## Cost envelope before preparation

Per cell: 256 families, 256 pairs, 512 cases, 3,072 planned requests.
Per logical model run: 19,456 requests. Total: **58,368** requests.
Configured output cap: **119,537,664 tokens** (requests × 2048), excluding
input and server-specific hidden/reasoning accounting. This is a request cap,
not measured usage. With three configured automatic attempts per job:
**175,104 attempts**, at most **358,612,992 requested output tokens** under
automatic retry cycles. Timeout/connection/rate-limit/unavailable are retryable;
model errors and wrong reasoning do not trigger quality retries. Resuming
finalized jobs creates no requests. Default indeterminate policy halts; explicit
indeterminate retry starts another cycle in the existing runner, so repeated
manual authorizations have no finite total upper bound. Their unknown costs
remain in the journal. No inference time, throughput or monetary cost is known.

## Prospective analysis

The existing `AnalysisPlan` in `analysis.template.json` contains logical run names
qwen, gemma and gpt-oss. Primary metric: MUS Exact Match on all UNSAT attempts
under existing metric definitions, including invalid/refused/error outcomes as
already specified. Additional: MUS F1, SAT accuracy and coverage. Existing
diagnostic error buckets, token usage and timings are descriptive; missing usage
is unknown and never zero-filled. No changes to metric definitions.

All 69 primary contrasts are enumerated before responses: 57 within-model/cell
strategy contrasts, **z3−direct**, and 12 noise endpoint contrasts (each model,
chain/math and strategy), **N32−N8**. Each has 256 UNSAT pairs. The N16 noise
point, K sweeps and topology panel receive separate cell estimates. No paired
K contrast, pooled topology effect, cross-model effect or post-hoc contrast
selection. K trends and panel differences are descriptive cellwise comparisons,
without new significance tests.

Use existing pointwise 95% Wilson for per-cell primary proportions and
whole-family percentile bootstrap for paired differences and supported
additional metrics: 10,000 repetitions, seed **20261128**. Both sides use the
same family multiplicity. Intervals are pointwise, not simultaneous; with
69 contrasts there is no familywise-error guarantee. No binary discovery
threshold or ranking claim is pre-registered. Degenerate bootstrap results
remain labeled and do not imply equivalence or population perfection.

Report every model/strategy/cell with its denominator, independent family count
and interval. Weight each family equally within its cell. Do not pool N variants,
series, topologies or models into an overall success rate. Existing summary
tables retain their full dimensions. Missing pairs or incomplete primary runs
block primary analysis; diagnostic views never substitute for completion.

`release-initialize` initializes existing runner UUIDs without HTTP, validates
selectors/complete inventories, substitutes only logical run names, and saves
`analysis.bound.json`, template hash and binding receipt before the first HTTP.
It cannot change metrics, sampling, models, contrasts, weights or statistics.
`release-resume` rechecks freeze, admission, binding and evidence before delegating
to the existing runner. Use the bound plan for the subsequent existing analyzer.

## Preparation and failure policy

Exactly one confirmation preparation is authorized for this release. Preserve
every cell, combined file, independent SMT reference, diagnostic and failure.
No seed search, sample expansion, failed-cell removal or threshold increase.
Leakage threshold remains 0.55. A failed gate blocks the dataset and launch.
Neither a small-sample fluctuation nor a systematic surface cue is declared as
the cause without a separate investigation; a failing score alone establishes
neither. Future investigation must retain the original failed release and may
not relabel it usable. Dataset technical admission is distinct from scientific
protocol, profile completion, backend verification, real smoke and paper claims.

Science/configuration/source/dependency changes require a new release version.
UUID binding and append-only operator evidence do not change scientific content.
No secrets, public tags, GitHub Release or external archive upload are included.
