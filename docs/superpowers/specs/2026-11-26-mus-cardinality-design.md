# Exact MUS cardinality and leakage diagnostics

The first experiment-repair PR implements the approved review's generator work,
with the user's requested improvement to leakage control. No article edits or
model inference. Published v1 artifacts and old experiment reports remain immutable.

## Contract

- `mus_size` is the number of requirements in the unique expected UNSAT MUS.
- Direct supports K=2; chain K>=3; fork/coverage/idem K=3; merge K=4;
  strict numeric cycles K>=2. Fork retains two branches, hence needs N>=4.
- Record pattern, pair identity and generator version. Reject unsupported sizes,
  insufficient rule/predicate budgets, and invalid generation parameters.
- Preserve SAT/UNSAT pairing, exact N, reproducibility, minimality and uniqueness.
- Remove case/UUID epilogues from model prompts. Shuffle variable aliases as well
  as requirements. Apply label-independent Boolean sign substitutions and numeric
  comparison orientations, rendering the resulting formulas consistently.
- Leakage is a diagnostic, not proof of absence. Use pair-grouped CV and balanced
  accuracy (chance 0.5), retain positive-class F1 as a separately named legacy
  measurement. Default acceptance limit is 0.55; it is configurable, never a
  target optimized by retrying seeds. Failure/unavailable CV cannot pass.
- Report global and per-K scores, uncertainty across folds, and acceptance.
  Persist a rejected dataset's diagnostic artifacts before raising an error.
- New generation uses v2 filenames/version; old v1 remains readable by evaluation.

## Approaches

Relabeling old datasets would preserve misleading topology names and does not
implement requested generation. Reject it. Rejection-sampling seeds until a probe
passes would overfit the diagnostic. Reject it. Correct constructions plus
label-independent symmetries and honest measured acceptance is the chosen approach.

## Limits

This PR does not establish natural-language semantic validity, implement a new
sandbox/MUS extractor, or repair all statistical plotting scripts. It must explain
that old reports use incompatible K and that generated v2 data require a new run.
No promise that every finite sample scores exactly 0.5 or passes 0.55.

## Validation

TDD regressions for every supported topology/size, tight N budgets, unsupported K,
metadata, deterministic prompt identity, signed rule semantics, failed leakage CV,
known leak vs paired-identical text baselines, acceptance and legacy loading.
Offline multi-seed audits report all predeclared seeds, including failures.
