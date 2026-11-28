# Local models and bounded live smoke execution plan

> Execute the user's supplied eight-step specification in this session. No production changes are planned.

**Goal:** Verify the installed Qwen, Gemma and GPT-OSS conditions and either retain production smoke evidence or concrete pre-generation blockers.

**Architecture:** Reuse the admitted development parent, frozen selection, RunConfig, production inventory/initializer, snapshot verifier and standalone evidence checker. Keep raw inventories and initialized runs under the existing ignored development bundle; commit separate operator configs, observations, hashes and a candid report.

**Tech stack:** Existing Python environment and controlled runner; read-only LM Studio inventory, SDK template/tokenizer utilities, local SHA256.

**Spec:** User attachment `7c7ab8f4-81b4-4411-b0b7-b11b19b312e8/Вставленный текст.txt` supplied in this chat.

## Constraints and review focus

- Base is master after PR #9, checked head 40a36468042f3b7af74dbecbb7a3ef9647e568b4; use codex/verify-local-models-and-live-smoke.
- Preserve historical receipts, confirmation-v1, generator, leakage 0.55, metrics and article.
- Fixed eight cases, direct/z3, 16 jobs/model, 48 maximum generation attempts, max_attempts=1, no transport retries, indeterminate halt.
- Target inventory is all 2,048 parent cases without selection: 4,096 requests/model.
- Exact backend template/tokenization including schema overhead and maximum coverage must pass before generation.
- Do not load models through JIT if this could evict another user's model; unknown active conditions remain unknown.
- Do not fabricate accounting, real-HTTP attestation, completed checkpoints or diagnostic outcomes for blocked runs.

## Tasks

- [x] Verify clean checkout, merged PR, frozen byte hashes and saved parent availability; create requested branch.
- [x] Revalidate full parent/selection; capture read-only model/backend observations, files and SHA256, defaults and provenance.
- [x] Save separate operator configs and complete target/smoke request inventories with hashes; investigate supported exact counting.
- [x] Initialize three separate runs without HTTP, verify empty journals and 16 jobs each; save pre-generation gate decisions.
- [x] Resolve conditional execution: all three models blocked before generation; do not invoke production resume with pending jobs.
- [x] Resolve completed-run condition: none completed; save UUID-bound diagnostic plans only, without fabricated checkpoints/analysis/accounting/SmokeEvidence.
- [x] For blocked runs, save negative checker results and concrete blockers, without false attestations; no timing extrapolation without measured generation.
- [x] Verify tracked evidence hashes, historical/source immutability and relevant offline regressions; prepare commit and PR description for publication without merge.

## Execution rulings

- Work in the supplied clean checkout on the user-named branch; the user has authorized the concrete verification/PR workflow, so no design approval gate is added.
- Backend queries and tokenization are not generation attempts. Installing SDK utilities into an ignored, separate target directory does not alter the repository environment or lockfile.
- An initialized blocked run is pending, not a completed smoke. No-op generation resume is unsafe for pending jobs and will not be invoked to manufacture a checkpoint.
- All three initial runs remain blocked/not_verified with zero HTTP generation attempts. Full pre-commit pytest passed (498 collected); 84 targeted tests also passed. Independent review found no high/medium issues. Final commit and PR publication are recorded in the chat after verification.
