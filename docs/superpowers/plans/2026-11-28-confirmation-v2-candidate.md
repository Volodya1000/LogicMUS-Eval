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

- [ ] Test receipt tampering, repeated freeze/preparation and release masquerading; observe RED.
- [ ] Implement minimal freeze/verify/prepare helper with exclusive writes and pinned source/helper/contracts/environment.
- [ ] Generate v2 plan and AnalysisPlan IDs programmatically from v1; retain all 69 contrasts and other analysis settings.
- [ ] Pin confirmed PR #10 observations separately from unknown active facts; retain primary retries=3, proposed 2048 tokens/120s.
- [ ] Verify helper tests and write candidate receipt before any preparation output exists.

### Task 2: One preparation and actual-data audit

- [ ] Invoke production prepare_experiment exactly once behind an exclusive attempt marker; preserve every failure.
- [ ] Audit saved cells/combined, production and independent SMT, exact K/N/minimality/uniqueness, leakage, duplicate baselines, balances, family pairing, development overlap and actual inventory.
- [ ] Attempt production admission/preflight unchanged. Save exact request JSONL/digests only where admitted; record refusals otherwise.
- [ ] Save compact artifact index/SHA256 and separate machine-readable gates; raw data stay ignored/local.

### Task 3: Verification, independent review, PR

- [ ] Run pytest, ruff check/format, strict mypy, pylint and required hooks; preserve results.
- [ ] Independently review candidate, helper, raw data and provenance; address material findings without another preparation.
- [ ] Verify historical tracked and local evidence hashes unchanged.
- [ ] Document final-freeze order and current data-reuse limitations; create PR with actual 19-cell/idem results, counts, hashes, blockers and exact operator next step.

## Decisions / progress

- Work in the clean existing checkout on the requested new branch. Saved PR #10 runs contain absolute checkout paths; moving them would invalidate existing provenance. No worktree or historical rewrite is needed.
- PR #10 was initially open; waited for its operator merge, confirmed via GitHub, fetched actual master before creating the branch.
- Baseline pytest started before changes; parent admission rechecked (2048 cases); both v1 local archives present and hashed.
