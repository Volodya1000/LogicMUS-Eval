# Development infrastructure smoke, controlled-v2

The development smoke checks HTTP/JSON, Z3, journaling and resume. It is not a research sample and its outcomes cannot enter primary quality analysis. Passing mock regressions does not establish readiness for scale. Historical `releases/confirmation-v1` remains blocked and unchanged.

`configs/development-smoke-v2/protocol.freeze.json` fixes the parent plan, seeds, size and selection rule before the first preparation attempt. The parent uses controlled-v2, development seeds 424242 and 424244, and 128 pairs per seed: 256 independent families per topology, chain and math at K=4 and N=8,48. Four cells contain 2,048 cases; reuse across N gives 512 independent families overall. Do not automatically grow this parent or change seeds after a failed admission.

The parent size is chosen separately from the infrastructure queue. Each cell supplies 256 paired family groups for the existing five-fold word/char TF-IDF diagnostics, approximately 51 families per held-out fold, rather than two groups. This is an operational development audit size, not a power calculation or a promise to pass. Every original SMT, independent SMT, exact K/N, minimality, unique MUS, word/char TF-IDF (0.55), and artifact/hash check remains mandatory for every parent cell and the combined artifact. Failure anywhere blocks smoke before HTTP.

The frozen selection takes seed 424242, pair index 0, SAT and UNSAT, from every parent cell, in parent order. This produces exactly eight cases. All three model configs use the existing direct and Z3 strategies, one attempt per job: **16 requests per model, 48 requests in total** if all jobs execute. Resume of completed runs makes zero additional requests. An indeterminate request halts; a separately authorized retry can add an attempt and must remain in the journal. The parent itself is never enqueued by a smoke config. The selector never reads model responses.

The selected receipt saves exact case UIDs, parent manifest SHA, parent plan SHA, the rule, purpose and selection SHA. Each smoke config pins the selection SHA. Preflight, initialization, start and resume revalidate the full parent and exact deterministic membership. Editing a rule, receipt, parent, config or saved identity cannot silently continue a run.

The subset's admission is explicitly `not_admitted`; no standalone leakage `passed` is assigned to eight cases. It includes Boolean/numeric, both labels, both strategies, and the N=48 long-input cells. N=48 coverage is not proof of maximum token coverage: the actual tokenizer and chat template must account for every future target request and show that the selected smoke covers the maximum input within context and output budget. If that fails, the fixed smoke remains unverified. Do not silently substitute examples or truncate input.

## Offline preparation

The fixed parent was prepared once in this PR and passed full admission on that first attempt. `configs/development-smoke-v2/preparation.receipt.json` preserves its manifest/source/environment and artifact hashes, SMT counts and measured leakage scores. The raw parent bundle remains local and ignored; its receipt alone cannot substitute for the actual admitted files. All three configs already pin the tracked `selection.json` receipt. Real HTTP, actual-tokenizer accounting and backend verification remain `not_verified`.

The maximum mean balanced accuracy across all required lexical views was:

| Parent cell | Maximum score |
| --- | ---: |
| chain, K=4, N=8 | 0.5195324284 |
| chain, K=4, N=48 | 0.5000000000 |
| math, K=4, N=8 | 0.4944947210 |
| math, K=4, N=48 | 0.5002639517 |
| combined | 0.5096611460 |

All 2,048 cases passed the existing SMT and independent-reference checks. This development admission and the simple baselines do not establish absence of every possible cue. The source SHA in the parent receipt is the actual working-tree hash captured at preparation start while generation code was stable; it is preserved as recorded and is not presented as a final-commit source receipt or a frozen confirmation release.

The following offline commands document how to reproduce the fixed preparation on a fresh checkout without its local bundle. Do not repeat the already completed local preparation, overwrite its evidence, or tune seeds/size after a failure. Use the repository environment. These commands perform no inference and do not import the network client.

```powershell
python -m logicmus_eval.cli prepare-experiment --plan configs/development-smoke-v2/parent.plan.json --output-dir configs/development-smoke-v2/bundle/parent
python -m logicmus_eval.cli prepare-infrastructure-smoke --parent-manifest configs/development-smoke-v2/bundle/parent/series.manifest.json --rule configs/development-smoke-v2/selection.rule.json --output configs/development-smoke-v2/bundle/selection.reproduced.json
```

Preserve the resulting manifest and all checks. The frozen plan and rule must still match `protocol.freeze.json`. The second command generates the selection only if full parent admission passes. It also exposes the Python API `prepare_selection(parent_manifest, SelectionRule.model_validate_json(rule_bytes), output)` from `logicmus_eval.infrastructure_smoke`. The selection SHA must match the pinned value in each smoke config before initialization; there are no placeholder selection hashes in these prepared configs.

A fresh preparation on another source/environment can have a different parent manifest hash even when the generated cases match. Retain the checked-in selection and preparation receipts as historical evidence of this attempt. For the new local preparation, create separate operator config copies that point to its parent and `bundle/selection.reproduced.json`, and pin that receipt's actual SHA before initialization. Record this as a separate preparation with the same frozen plan/rule; never edit an old receipt checksum or reuse an initialized run with changed pins. A failed fresh admission still blocks all HTTP and does not authorize seed or size changes.

Inspect each config with `experiment-preflight --config ...`, then use `experiment-initialize --config ... --run-dir ...` to save a UUID, exact request inventory and empty journal without HTTP. A new run must use a new directory. Retain the same initialized run for execution and resume.

## Before real requests

An operator must verify each exact served model/revision or file, quantization, backend version, context, tokenizer and chat template. The supplied model aliases are prospective identifiers; they do not prove that those weights exist or are loaded. Fill missing expected-profile fields and verify generation settings, timeout and output cap before fixing each run. No actual-tokenizer or backend evidence is supplied by offline checks.

After these steps, explicitly run `experiment-resume --run-dir ... --config ...` on each initialized development run. This contacts the model. Do not run the whole parent. Retain all responses, refusals, incorrect answers, transport errors, truncation and context errors. Wrong SAT/MUS reasoning is a model outcome, not an infrastructure failure.

Copy the completed `report.json` to a named checkpoint inside the run, resume again, and save the after checkpoint. A no-op resume must preserve the full report, journal head/event count and every outcome. Prepare a diagnostic analysis plan from `analysis.template.json`, substituting the saved UUID only; analyze the run with `analyze-controlled`. The diagnostic output records provenance, completeness, error types and available timing/token/cost measurements. Empty or unknown usage must remain unknown. Run full primary-analysis regressions separately against the existing admitted mock fixtures.

## Evidence and remaining gates

New `SmokeEvidence` uses `evidence_version: infrastructure-smoke-v1` and binds `parent_manifest_sha256` and `selection_sha256`. Hash the selection receipt, parent manifest, checkpoints, accounting and diagnostic artifacts. The check validates complete journal provenance and actual HTTP-adapter envelopes. Every journal attempt must identify the real HTTP adapter; injected completions remain mocks even if they fabricate HTTP-looking envelopes. Missing origins in historical journals are not newly verified by this source version. Operator attestation cannot make mock envelopes real. Backend calibration revalidates any infrastructure selection against its admitted parent before use.

A future confirmation release must freeze its own scientific plan, parent plan and `smoke_selection_rule`. Its `datasets_admitted` gate always evaluates the full confirmation manifest; smoke evidence cannot replace it. The offline command `check-development-smoke --root configs/development-smoke-v2 --config configs/development-smoke-v2/qwen.smoke.json --evidence configs/development-smoke-v2/qwen.evidence.json` validates infrastructure evidence independently of any confirmation release. Repeat for each model. Missing or failed evidence yields `real_smoke: not_verified`. Neither this PR nor offline/mock evidence sets `real_smoke=passed`.

Remaining actions after this PR are: operator model/backend/tokenizer verification; a real admitted development smoke with 48 planned requests and its diagnostic evidence; and a separately fixed/prepared new confirmation release. Do not regenerate or relabel confirmation-v1 and do not edit old source-receipt checksums to match new sources. Old frozen receipts may require checkout of their original commit.
