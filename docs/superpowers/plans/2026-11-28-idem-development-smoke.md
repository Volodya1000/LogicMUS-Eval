# Idem v2 and development infrastructure smoke

> **For agentic workers:** Use test-driven development and independent review. The supplied user specification is authoritative; implement the authorized PR without merge.

**Goal:** Remove the idem duplicate-formula cue in a new controlled protocol, and run a fixed small infrastructure selection only through an admitted development parent.

**Architecture:** Preserve controlled-v1 generation and historical releases. Add controlled-v2 identities and an explicit infrastructure-smoke-v1 selection receipt. Runner admission always verifies the entire parent, then validates the deterministic selection. Existing inference, journal, Z3 and diagnostic analysis are reused.

**Tech stack:** Python, Pydantic strict models, pytest, independent SMT/Z3, existing word/char TF-IDF.

## Global constraints

- No real LLM calls, model downloads, large run or new confirmation preparation.
- Preserve releases/confirmation-v1 bytes and blocked status, scientific metrics, strict typing and leakage threshold 0.55.
- Parent size, seeds and smoke selection are fixed before preparation; failed admission blocks execution without seed tuning or automatic growth.
- A smoke selection has no standalone research admission and cannot enter primary analysis.

## Design decisions

The user already specifies the formal pair and parent/selection architecture. Implement those directly. A separate runner protocol is scoped to infrastructure-smoke-v1, with an optional strict smoke-selection path in RunConfig; legacy config serialization must preserve absent fields in historical hashes. Selection receipts bind parent manifest SHA, plan SHA, exact ordered UIDs, purpose, selection rule, and their digest. The receipt is recomputed against the full parent on every preflight/start/resume. Development configs live outside the historical release.

## Review focus

- Historical saved manifests retain original absent optional fields during hash verification.
- Parent failed cell admission cannot be bypassed by selecting other cells.
- A valid UID with changed selected content or selection parameters is rejected before HTTP.
- Smoke results cannot silently pool with scientific runs or count as datasets_admitted.
- Offline paths must never import a network client or call an endpoint.

## Task 1: Controlled-v2 and duplicate audit

- [x] Reproduce legacy SAT duplicate implications on a small fixture and record original smoke leakage failure.
- [x] Add failing tests for v2 pair, identities, text/polarity agreement, nested noise, independent exact K/minimal/unique SMT.
- [x] Version generation, identity and provenance without changing v1 output; add offline duplicate baselines with confusion matrices and balanced accuracy.
- [x] Validate fixed development seeds and multiple N; retain TF-IDF audit unchanged.

## Task 2: Parent-bound infrastructure selection and runner

- [x] Add negative tests for failed leakage/hash admission, unknown/altered UIDs, purpose, selection hash/config changes, exact small queue and resume.
- [x] Implement strict InfrastructureSelection and SelectionRule models in logicmus_eval/infrastructure_smoke.py, prepare_selection(parent_manifest, rule, output), and validate_selection(parent_manifest, selection_path, cases).
- [x] Bind selection, parent and purpose into run identity; retain saved optional-field compatibility; prohibit primary smoke analysis.
- [x] Exercise mock runner/journal/no-op resume and offline imports.

## Task 3: Release evidence, fixed configuration and documentation

- [x] Add regressions for diagnostic smoke evidence, real HTTP requirement and longest-input accounting.
- [x] Update check_backend/check_smoke with explicit versioned evidence; preserve legacy evidence reading, strict confirmation admission and historical receipts.
- [x] Freeze separate controlled-v2 development parent and deterministic smoke rule/configs; justify parent size independent of infrastructure sample.
- [x] Document exact future request counts and remaining operator/backend, real smoke and future confirmation steps.

## Task 4: Verification and PR

- [x] Run complete pytest, strict mypy, ruff and relevant pylint checks; review diff and historical artifacts.
- [x] Independent review of security/admission/identity boundaries; fix findings with regressions.
- [ ] Commit and open PR against master without merge, including limitations and evidence.

## Execution notes

- Baseline: 447 tests passed on master before changes.
- Reproduced both original defects before implementing the new contracts.
- Independent review reproduced two additional gaps: injected legacy HTTP envelopes and mixed protocols across distinct models. Both received failing regressions and fixes.
- One fixed development parent preparation passed all existing checks; original source/artifact hashes retained. No LLM/model download/confirmation preparation occurred.
- Scope: use the requested clean branch in the supplied checkout; keep all historical release files unchanged.
- Fixed a Windows UTF-8 read in the new tampering regression after the full suite exposed it.
- Scoped Git attributes preserve the three pre-preparation byte-bound JSON artifacts exactly; no checksum rewriting.
