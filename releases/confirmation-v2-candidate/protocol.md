# Confirmation-v2 scientific candidate — controlled-v2

This directory freezes a scientific candidate only. It is not a release manifest,
admission, final RunConfig freeze or permission for initialization/inference.
V2 corrects the idem construction after v1 failed validation. It is not an
independent replication of v1. V1 and its historical failure remain unchanged.
The original scientific grid, seeds, pairing, metrics and 69 prospective contrasts
are retained. Cell/family identities use production controlled-v2 code.

The candidate receipt pins science, source, dependencies and initial inventory
before exactly one offline preparation. Proposed configs are reviewable future
conditions, not calibrated executable-release assertions. Subsequent release
instructions in the inherited scientific design describe future requirements.

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

## Models and proposed conditions

Retain Qwen2.5-Coder-14B, Gemma-4-E4B and GPT-OSS-20B; direct/z3.
`model-facts.json` imports the exact PR #10 observation records with source
hashes, dates and limitations. Files/SHA256 and quantization are confirmed
historical observations. Qwen context 12288 was observed on that instance;
Gemma/GPT-OSS were installed/exposed but not loaded. No historical observation
is a new attestation of current active backend, template, runtime or defaults.
The selected installed runtime is not a verified active runtime. Embedded GGUF
templates are not proven active, especially Gemma with its Hub override.
Unknown active facts remain null in proposed configs.

Proposed conditions retain max_tokens=2048, temperature=0, top_p=1, generation
seed/reasoning_effort unset, timeout=120s, Z3 timeout=5s. The 2048 output cap
and 120s timeout still need development calibration. Main retry policy remains
three automatic attempts for transient errors, not smoke max_attempts=1.
No correctness-based retries or post-result calibration on confirmation.

Two independent requirements apply:
1. Standalone development-smoke must cover the full fixed admitted development
   parent, using its existing fixed selection and exact HTTP input accounting.
   The old template-only diagnosis remains negative: target/smoke maxima are
   direct 2444/2302 and z3 3791/3672. No subset is changed to obtain passed.
2. Release-smoke must cover the exact future confirmation requests for every
   model/strategy under the finalized conditions. Passing requirement 1 does
   not establish requirement 2, nor conversely.

SDK apply_prompt_template/tokenize counts are template-only. They do not measure
full HTTP input accounting, and response_format/schema overhead is unknown,
not zero. Full input plus output cap must fit verified active context. Calibrate
truncation/timeouts on development before final RunConfig freeze. Existing v1
budget-selection rules and all context/HTTP/provenance checks remain binding.
If a different smoke selection is necessary, a separate next-PR proposal must
retain the old failed evidence, define and freeze a new prospective rule and
validate both requirements independently. This candidate changes no selection.

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
