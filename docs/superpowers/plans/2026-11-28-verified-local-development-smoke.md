# Verified local development smoke implementation plan

**Goal:** Prepare PR 12 against master after PR 11, with three-model backend observations, versioned input-only smoke selection, and real development measurements where gates permit.

**Spec:** The user's supplied request, preserved locally with this task. Its limits take precedence over workflow defaults.

**Architecture:** Preserve immutable historical receipts and exact available sources before production edits. Add a v2 selector alongside v1, binding all parent request measurements and their inference/tokenizer conditions. Use existing HTTP adapter, journal, admission and smoke checker; missing full accounting remains a blocker.

**Constraints:** No confirmation generation; no dataset preparation or seed search; no article/candidate edits; no vLLM or parallel runner; no weakened checks; at most 12 diagnostic + 84 smoke attempts across all runs, including errors/timeouts; retries disabled. No merge, tag, Release or artifact upload. ready_for_scale remains blocked.

- [x] Fetch actual master, create requested codex branch, inspect historical failures and existing admission/evidence paths.
- [x] Archive exact pre-edit source bytes and inventory; preserve all historical hashes and distinguish unrecovered development preparation bytes.
- [x] Add v2 input-maximum selection with deterministic tie-break and deduplication; keep original eight cases and v1 behavior. RED/GREEN tests for tampering, admission, ties and missing coverage. Independent review added the required immutable v1 base receipt pin.
- [x] Observe sequential LM Studio instances, load configuration, runtime, template/tokenizer and requested/effective reasoning settings. Installed source and native ABI/call-chain verification established scoped full HTTP accounting.
- [x] Freeze safe development diagnostic budgets before up to 12 HTTP attempts; retain responses, usage, elapsed times, logs and a persistent global ledger. Ten actual diagnostics, no retries.
- [x] Measure all existing parent and candidate inputs offline, freeze v2 rule/configs/selection, evaluate the two coverage gates independently. Eleven cases, 66 smoke requests, all six scope maxima covered under saved conditions/date.
- [x] Execute only admitted development smoke requests within shared cap; verify completed no-op resume and diagnostic analysis. All 66 requests executed; Qwen/GPT passed, Gemma retained one truncation and received no SmokeEvidence.
- [x] Run suite, ruff, mypy, pylint and project hooks; independently review branch, inventory protected bytes and request ledger, write compact RESULTS and hashes. Total 76/96 development attempts, zero confirmation generation, zero retries.

Delivery is recorded by the resulting commit, pushed branch and open PR; no merge
or executable release is part of this task.

**Recorded limitations:** The exact intermediate development-parent source hash
`595ec63f...` could not be recovered; its original receipt/hash remain intact.
All 130 historical candidate repository inputs match the preserved source archive.
New execution source is archived separately (`a327cc5f...`). Gemma's frozen 4096
output cap truncated one development response: retain its complete failed smoke,
no-op resume and diagnostic analysis; do not manufacture real SmokeEvidence or
retune/retry the run. GPT-OSS's dynamic template date also needs a prospective
multi-day release policy. Source/core hooks passed, with 549 tests collected.

**Review focus:** Length or tokenizer substitution, rehashed selection/request tampering, inadmissible full parent, missing confirmation coverage, mocked/empty HTTP journals, restart bypass of attempt cap, and historical source mismatch.

**Execution:** Selector and offline regressions can proceed independently of backend research (parallel-agents skill). Only the root worker may issue real generation or load/unload calls. No production change is allowed to relabel template-only counts as full HTTP accounting.
