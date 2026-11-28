# Confirmation-v2 offline scientific candidate: blocked for scale

Base: master after PR #10 (`040052fe392d2823a379513aa934ca72469a9c9d`).
Scientific contracts and receipt were committed in `07ffaa1` before the one
production preparation began. This is a corrected construction following v1's
validation failure, **not an independent replication of v1**.

## Actual preparation and data

Exactly **one** production offline preparation. No seed search, sample expansion,
cell removal, threshold change or second attempt. All raw results remain local
under `bundle/`; `artifact-index.json` records their sizes and SHA256.

Production dataset admission: **passed**; separate saved-data audit: **passed**.
Observed: **19 cells, 9728 cases, 2816 unique families**, 4864 SAT / 4864 UNSAT.
Planned requests from actual cases: **58368**; maximum configured automatic attempts: **175104** (main policy max_attempts=3, not smoke max_attempts=1).
Explicit repeated indeterminate retries have no finite total bound; default policy remains halt.

| Series | Pattern | K | N | Cases / families | SMT / saved replay | Leakage max BA | Leakage |
|---|---|---:|---:|---:|---|---:|---|
| noise-chain | chain | 4 | 8 | 512 / 256 | passed | 0.5078431373 | passed |
| noise-chain | chain | 4 | 16 | 512 / 256 | passed | 0.5000000000 | passed |
| noise-chain | chain | 4 | 32 | 512 / 256 | passed | 0.5019230769 | passed |
| noise-math | math | 4 | 8 | 512 / 256 | passed | 0.4901960784 | passed |
| noise-math | math | 4 | 16 | 512 / 256 | passed | 0.4901960784 | passed |
| noise-math | math | 4 | 32 | 512 / 256 | passed | 0.5000000000 | passed |
| size-chain | chain | 3 | 16 | 512 / 256 | passed | 0.5058069382 | passed |
| size-chain | chain | 4 | 16 | 512 / 256 | passed | 0.5000000000 | passed |
| size-chain | chain | 6 | 16 | 512 / 256 | passed | 0.5000000000 | passed |
| size-math | math | 2 | 16 | 512 / 256 | passed | 0.4864253394 | passed |
| size-math | math | 4 | 16 | 512 / 256 | passed | 0.4901960784 | passed |
| size-math | math | 6 | 16 | 512 / 256 | passed | 0.5234162896 | passed |
| topologies | chain | 4 | 16 | 512 / 256 | passed | 0.5000000000 | passed |
| topologies | coverage | 3 | 16 | 512 / 256 | passed | 0.5000000000 | passed |
| topologies | direct | 2 | 16 | 512 / 256 | passed | 0.5216817496 | passed |
| topologies | fork | 3 | 16 | 512 / 256 | passed | 0.5000000000 | passed |
| topologies | idem | 3 | 16 | 512 / 256 | passed | 0.5098039216 | passed |
| topologies | math | 4 | 16 | 512 / 256 | passed | 0.4901960784 | passed |
| topologies | merge | 4 | 16 | 512 / 256 | passed | 0.5057692308 | passed |

### Idem and integrity checks

- Idem exact_text: BA=0.5000000000; confusion (gold→prediction) `{"SAT": {"SAT": 0, "UNSAT": 256}, "UNSAT": {"SAT": 0, "UNSAT": 256}}`.
- Idem canonical_formula: BA=0.5000000000; confusion (gold→prediction) `{"SAT": {"SAT": 0, "UNSAT": 256}, "UNSAT": {"SAT": 0, "UNSAT": 256}}`.

`data-audit.json` preserves every cell's production flags, failures, required
direct/z3 and primary lexical views/groups, fold scores, actual K/N and rule-ID
checks, expected case membership/provenance, duplicate baselines, independent
saved-representation replay, family balance and stable-insertion checks.
Overall independent checks: `{"all_cells_checked": true, "combined": true, "expected_inventory": true, "frozen_plan_matches": true, "frozen_source_matches": true, "no_development_overlap": true, "only_expected_case_copies": true, "production_manifest": true, "stable_insertion": true}`.
Independent SMT checks the saved full instance and expected core; SAT after deleting
each expected member from the full UNSAT instance proves minimality and uniqueness.
Cross-series copies are reported separately and retained as registered cells;
combined is checked against ordered source cells and creates no extra requests.
Passing these probes is not proof of absence of all leakage.

## Proposed requests and remaining gates

`request-inventory.json` records unchanged production preflight outcomes. Exact
request JSONL is stored only when production admission succeeds; its bytes,
per-request digest and aggregate production digest are retained. These requests
are exact for the proposed configs, not a final calibrated release freeze.
No SDK template-only value is labeled full HTTP accounting. Schema overhead is unknown.
No generation, real smoke, experiment-start/resume, release-resume, model loading
or unloading was performed. No SmokeEvidence, archive, Release or tag was created.

| Gate | Status |
|---|---|
| scientific_candidate_frozen | passed |
| datasets_admitted | passed |
| profiles_complete | blocked |
| exact_input_accounting_verified | not_verified |
| real_smoke | not_verified |
| ready_for_scale | blocked |

Remaining blockers:

- `PROFILES_EFFECTIVE_BACKEND_UNKNOWN`: Active tokenizer/template/runtime/context and omitted effective defaults require current per-model evidence; PR #10 records are historical observations.
- `HTTP_INPUT_ACCOUNTING_MISSING`: Full exact HTTP prompt accounting, including response_format/schema overhead, is unknown. SDK template-only counts are not full HTTP input accounting.
- `STANDALONE_SMOKE_FULL_PARENT_COVERAGE_UNVERIFIED`: The original fixed selection remains unchanged. PR #10 Qwen template-only maxima target/smoke: direct 2444/2302, z3 3791/3672. Preserve this negative diagnosis; it cannot be converted into exact accounting or coverage.
- `RELEASE_SMOKE_CONFIRMATION_COVERAGE_UNVERIFIED`: Release smoke must cover exact confirmation inputs per model/strategy under final calibrated conditions, independently from standalone-parent coverage.
- `DEVELOPMENT_CALIBRATION_MISSING`: 2048 output tokens and timeout 120s are proposed conditions, not development-confirmed. Latency, truncation and timeouts have not been measured.
- `REAL_SMOKE_MISSING`: Zero generation attempts; no real SmokeEvidence, completed no-op resume or diagnostic analysis. No smoke evidence was manufactured.
- `FINAL_EXECUTABLE_RELEASE_NOT_FROZEN`: Intentional scientific candidate only. Final RunConfigs, release manifest, UUID binding and release admission do not exist.
- `CANDIDATE_REUSE_HANDOFF_UNSUPPORTED`: Current CLI lacks a candidate-provenance import/handoff verifier. Reuse needs a reviewed immutable-byte/source/environment/provenance handoff; never edit checksums or rerun preparation to seek passage.

**Exact next operator action:** Establish full HTTP schema-inclusive input accounting and current effective backend profiles before authorizing any real smoke; retain the old fixed-selection negative evidence and resolve both independent coverage gates. See FINALIZATION.md.

The complete final-freeze order, separate smoke requirements, future-selection
proposal and candidate-data handoff limitation are in [FINALIZATION.md](FINALIZATION.md).
Current candidate receipt cannot authorize release initialization/resume.

## Hashes and delivery

- candidate_receipt_file_sha256: `da362976e77a76feff63756cda4a4a7d2990cceac0f6e6eb9fa4cd2d0b88c567`
- scientific_plan_sha256: `3f4683bcb9226ac1c88d5676e6ce1b2145298e33ed3abbb3bfa121a57e70da16`
- analysis_sha256: `98d3cb0b200777fbdb680bea83f7d282c56ce621bf4fdb23866e2f7cc7e4b6f8`
- source_bundle_sha256: `9434b557c876a3a3a51864fe5bd8a010f914044cc3805041f669f142d105a642`
- uv_lock_sha256: `19eeec34ea89ff27857c44ae2373a2df6d389bdd28d3409b5d05955a07d635f5`
- series_manifest_sha256: `a518f0556244befe280a77d323d7e937cc35472f0365a8c801f886710a575d8b`
- data_audit_sha256: `6f8c3da4f67e9227f57177df4438882be66c7f779620cd16588262e9f2bdd3b0`
- raw_artifact_index_sha256: `b00dd3c00a253d3551dac8f520fa00f5a706ad277979453670904b0bdd167b25`

Raw local delivery: 46 files, 627109711 bytes. No archive/upload.
The compact Git files do not replace the ignored raw bundle. Historical byte
integrity is recorded in `historical-integrity.json`; the candidate source
package and dependency lock remain unchanged from the PR #10 base.
Regression commands, independent review and Git-byte verification are recorded
in `verification.json`.
