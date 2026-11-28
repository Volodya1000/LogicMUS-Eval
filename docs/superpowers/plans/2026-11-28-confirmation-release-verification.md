# Confirmation release execution ledger

Plan: `2026-11-28-confirmation-release.md`; full requirements supplied by user.

- Base verified by git fetch: master 71f5e7b1d7528f4e081b825a91a30a4289a184f5.
- Work performed in requested branch codex/freeze-confirmation-release; clean
  original checkout, no worktree needed and no historical artifact changes.
- Task 1: inventory and prospective selectors implemented; seven tests initially
  passed after observing missing-module failures. Chain's supported floor is K=3;
  corrected the proposed grid before generating or preparing any cases.
- Task 2: existing new-run setup extracted into initialize_run; runner regression
  and binding tests passed (40). No inference import/HTTP during initialization.
- Task 3: offline freeze/evidence/gates implemented. Independent read-only review
  found empty calibration, stub analysis, unlocked binding persistence,
  group-wide incompatibility and missing gated indeterminate retry support.
  Reproduced substantive findings with failing tests, then fixed them. Added
  truncation/timeout calibration regressions. New test file: 29 passing tests.
- Full project suite before final calibration additions: 445 passed. Final hooks
  rerun the full suite. Mypy: 129 source files; ruff clean; source pylint 10/10.
- Git hooks initially could not rebuild editable metadata because proxy to PyPI
  was unavailable. Verified UV_NO_SYNC is supported, used existing installed
  dependencies, and kept actual hook checks. Test-file lint conventions corrected.
- Science frozen before the one explicit prepare-experiment invocation. Seeds,
  size and threshold never adjusted. No model calls, downloads or real smoke.

Implementation decisions under the user's explicit brief: preserve three old-grid
models; recommend 256 families per cell; separate descriptive K/panel estimates
from paired contrasts; require operator attestation plus saved evidence instead
of impossible server echo; keep all failed artifacts local with hashes.

The reviewer deferred final dataset/archive/document results because they were
not yet generated. These are checked by the final offline preparation and
copy-integrity inspection; real backend identity and smoke remain not_verified.
No review minors were deferred.
