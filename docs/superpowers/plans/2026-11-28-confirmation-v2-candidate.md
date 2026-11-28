# Confirmation-v2 offline candidate implementation plan

> **For agentic workers:** Execute inline using superpowers:executing-plans; use a fresh independent reviewer at the end.

**Goal:** Freeze and audit one controlled-v2 scientific candidate without authorizing inference.

**Architecture:** Preserve the confirmation-v1 design and use production identities, preparation, admission and preflight unchanged. A small standalone candidate receipt helper pins science/source/dependencies before preparation; it is deliberately outside release-freeze and cannot establish release admission.

**Tech Stack:** Existing Python 3.13, Pydantic, Z3 and sklearn; existing installed lockfile environment.

**Spec:** User's PR #11 request; scientific details remain in the candidate protocol.

## Global constraints

- Base: master after PR #10, 040052fe392d2823a379513aa934ca72469a9c9d.
- Branch codex/prepare-confirmation-v2; create PR, never merge.
- Exactly one preparation, seeds 2718281/3141593, 128 pairs/seed, threshold 0.55, all 19 cells in production order.
- No model generation, experiment start/resume, release resume, model loading/unloading, archives, tags or releases.
- Preserve article, confirmation-v1, historical evidence and all production gates.

## Review focus

- Changed plan/source/lock/environment must invalidate the candidate receipt.
- Second freeze/preparation must fail without overwriting the first attempt.
- Candidate must fail production release initialization and never manufacture admission.
- Failed cells must survive with complete diagnostics, including idem and combined.
- Saved requests must come from admitted production preflight or retain an explicit blocker.

### Task 1: Immutable scientific candidate

Files: scripts/confirmation_candidate.py; tests/unit/test_confirmation_candidate.py; releases/confirmation-v2-candidate/{confirmation.plan.json,analysis.template.json,protocol.md,*.proposed.json,inventory.before-preparation.json,candidate.receipt.json}.

- [x] Test receipt tampering, repeated freeze/preparation and release masquerading; observe RED.
- [x] Implement minimal freeze/verify/prepare helper with exclusive writes and pinned source/helper/contracts/environment.
- [x] Generate v2 plan and AnalysisPlan IDs programmatically from v1; retain all 69 contrasts and other analysis settings.
- [x] Pin confirmed PR #10 observations separately from unknown active facts; retain primary retries=3, proposed 2048 tokens/120s.
- [x] Verify helper tests and write candidate receipt before any preparation output exists.

### Task 2: One preparation and actual-data audit

- [x] Invoke production prepare_experiment exactly once behind an exclusive attempt marker; preserve every failure.
- [x] Audit saved cells/combined, production and independent SMT, exact K/N/minimality/uniqueness, leakage, duplicate baselines, balances, family pairing, development overlap and actual inventory.
- [x] Attempt production admission/preflight unchanged. Save exact request JSONL/digests only where admitted; record refusals otherwise.
- [x] Save compact artifact index/SHA256 and separate machine-readable gates; raw data stay ignored/local.

### Task 3: Verification, independent review, PR

- [x] Run pytest, ruff check/format, strict mypy, pylint and required hooks; preserve results.
- [x] Independently review candidate, helper, raw data and provenance; address material findings without another preparation.
- [x] Verify historical tracked and local evidence hashes unchanged.
- [ ] Document final-freeze order and current data-reuse limitations; create PR with actual 19-cell/idem results, counts, hashes, blockers and exact operator next step.

## Decisions / progress

- Work in the clean existing checkout on the requested new branch. Saved PR #10 runs contain absolute checkout paths; moving them would invalidate existing provenance. No worktree or historical rewrite is needed.
- PR #10 was initially open; waited for its operator merge, confirmed via GitHub, fetched actual master before creating the branch.
- Baseline pytest started before changes; parent admission rechecked (2048 cases); both v1 local archives present and hashed.
- Task 1 complete in 07ffaa1, before preparation: baseline 498 passed; helper 9 passed; full commit hooks passed (507 tests collected); Ruff check/format, strict mypy (137 files) and full production pylint passed.
- Independent reviewer found installed transitive dependencies were missing from the original environment check. A real injected dist-info regression failed, then passed after full installed-distribution inventory was added before freeze.
- Ruling: preserve separate candidate and executable release lifecycles; current CLI has no provenance-verifying candidate-import command. Document the handoff limitation rather than modify release-freeze or checksums.
- Preparation attempt 1 started only after scientific freeze commit, with an exclusive durable marker. No repeat or parameter changes are authorized.
- Independent pre-run audit review requested explicit missing-artifact diagnostics and actual-row K/N/provenance/membership checks; these were added to the saved-data audit without changing production preparation.
- Preparation session 27073 completed successfully, 2026-11-28T14:47:31Z. Never start another prepare. Raw stdout/stderr retained in bundle/logs and experiments/confirmation-v2-preparation.{stdout,stderr}.txt. Final production manifest: 19/19 SMT/reference/leakage passed, combined passed, ready_for_evaluation=true. Manifest SHA256 a518f0556244befe280a77d323d7e937cc35472f0365a8c801f886710a575d8b.
- Independent raw-data reviewer verified 19/9728/2816, 4864 SAT and UNSAT, all expected IDs/provenance/K/N, all 9728 stored SMT representations, family pairing and combined equality. Idem 512 independent SMT checks passed; both duplicate cues BA=0.5 with zero duplicate predictions. Final production leakage admission remains pending until manifest exists.
- Task 2 complete: final manifest and separate full saved-data SMT replay/audit passed; all 258 required lexical measurements passed. Actual counts 19/9728/2816 and 58368 requests; main retry limit175104. Exact production preflight inventories saved19456/model. Local raw index46files627109711bytes; all174 historical baseline hashes unchanged, plus saved-index checks64/10/90 all matched.
- Final gates: scientific_candidate_frozen=passed, datasets_admitted=passed; profiles_complete=blocked, exact_input_accounting_verified=not_verified, real_smoke=not_verified, ready_for_scale=blocked. No executable release frozen or initialized.
- Final independent review complete: all58368 exact requests/jobs/digests and production identities matched fresh preflight; raw index46files627109711bytes independently verified; no remaining material findings. Source/protocol/analysis were not changed after freeze. Verification commands and evidence captured in verification.json.
