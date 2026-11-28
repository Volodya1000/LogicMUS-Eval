# Verified local development smoke, selection v2

This infrastructure-only protocol extends the historical eight-case selection
without changing its receipt, admitted parent, scientific data or negative PR10
results. Actual execution results and limitations are recorded in
[RESULTS.md](../configs/development-smoke-v2/verified-local/RESULTS.md).

`infrastructure-smoke-v2` is a **selection** version. The established runner,
HTTP-adapter, journal and `infrastructure-smoke-v1` evidence envelope remain in
use. No confirmation release is admitted by this change.

The new rule requires two immutable file pins: `base_selection` identifies the
historical v1 receipt, and `measurement_manifest` identifies all six full-parent
input inventories. The validator rechecks the complete development parent,
reconstructs the v1 receipt, preserves its eight UIDs in order, and checks the
three models and both direct/z3 strategies. Each inventory covers every admitted
parent UID exactly once and binds the actual production request digest, positive
input length, tokenizer, template, RunConfig and external accounting proof.
For each scope it selects maximum input length, breaking ties by lexical
`case_uid`, then deduplicates those six maxima against the original eight.
At most 14 cases and 84 single-attempt smoke jobs are possible. The existing
Boolean/numeric, SAT/UNSAT, admission, artifact and provenance checks remain.

The external measurement attestation is a prerequisite whose implementation and
verification artifacts must be reviewed. Hashes and coverage booleans alone do
not establish exact counting. Synthetic test inventories exercise validation
and never authorize real HTTP or qualify as real smoke.

For the installed LM Studio 0.4.13+1 / llama.cpp CUDA12 2.83.0, a narrowly scoped
method was established by inspecting the exact application and native binaries.
The HTTP handler converts the two response schemas to sampler grammar. Prompt
formatting receives raw effective base/session configuration, explicit reasoning
and HTTP overrides, and the prediction formatter's BOS/EOS options. The exact
installed `llama.dll` then tokenizes its formatted text with the prediction
engine's native special-token flags. Vocabulary-only loading avoids tensors and
inference contexts. Binary hashes, ABI disassembly, template/config snapshots
and actual input/usage traces support this path. A public SDK template-only
count is insufficient: Gemma's default thinking template and BOS behavior
demonstrated a concrete mismatch. Fixed examples with equal usage provide
diagnostic checks; the inspected implementation and native path establish the
method's restricted scope.

This method applies to the saved single-user text-only requests, exact schemas,
model files, templates, backend and rendered date. Changes to these conditions
require renewed verification. The dynamic date in GPT-OSS's system prompt is
part of its measured input; the multi-day release still needs an explicit
clock/template policy. Today's exact count table cannot silently authorize
requests rendered on another date. Full-parent coverage and future confirmation-input
coverage are computed and reported separately. Confirmation is inspected only
offline, using the new prospective development conditions; its prepared files
and proposed configs remain unchanged.

Before execution, the new configs, selection, accounting, source archive, UUIDs
and 96/12/84 attempt limits are frozen. A persistent shared budget reserves each
generation attempt before the original urllib HTTP adapter opens its request.
The serial production runner is unchanged. Automatic retries are disabled,
indeterminate work halts, and new runs cannot repeat reserved smoke requests.
Every model response and processing failure remains in the production journal.
Completed no-op resume must preserve reports, journal and outcomes while adding
zero generation attempts. The unchanged production checker independently verifies
the evidence, diagnostic analysis and accounting. Evidence files are written
only after that check succeeds.

Historical sources and new execution sources have separate inventories and
archives. Saved-data revalidation does not assert preparation-source equality.
The exact historical development working tree could not be recovered; its
original hash remains unchanged and the gap is reported. Candidate source
bytes are preserved independently. Final executable release creation and the
candidate-to-release handoff remain a separate, blocked stage.
