# Offline idem evidence

The historical controlled-v1 defect was reproduced before changing generation.
Only the frozen idem K=3 N=16 cell was regenerated for this audit (512 cases,
256 families); this did not prepare a new confirmation release. The historical
release directory and source receipts were left untouched.

Both fixed baselines predict SAT if a duplicate exists and UNSAT otherwise.
Their features consume rules alone; labels enter only the confusion matrix.
The matrix uses gold rows and predicted columns, ordered SAT, UNSAT.

| Dataset | Cases / families | Exact-text confusion | Exact-text balanced accuracy | Canonical-formula confusion | Formula balanced accuracy |
| --- | --- | --- | --- | --- | --- |
| Historical controlled-v1 idem N=16 | 512 / 256 | [[83, 173], [0, 256]] | 0.662109375 | [[256, 0], [0, 256]] | 1.0 |
| Fixed development controlled-v2 N=3 | 8 / 4 | [[0, 4], [0, 4]] | 0.5 | [[0, 4], [0, 4]] | 0.5 |
| Fixed development controlled-v2 N=16 | 8 / 4 | [[0, 4], [0, 4]] | 0.5 | [[0, 4], [0, 4]] | 0.5 |
| Fixed development controlled-v2 N=48 | 8 / 4 | [[0, 4], [0, 4]] | 0.5 | [[0, 4], [0, 4]] | 0.5 |

The three development cells contain 24 cases in total, with the same four
families reused across N. Seeds [42, 44, 424242, 424244], one pair per seed,
and N=[3, 16, 48] were fixed in the regression before generating the reports.
This is a construction audit, not a standalone admitted research sample.

Controlled-v2 uses UNSAT {a, a -> b, a -> not b} and SAT
{not a, a -> b, a -> not b}, followed by identical signed presentation draws.
The two implications have opposite consequents and the same antecedent;
each noise rule has a fresh variable disjoint from the construction. Thus the
absence of duplicated formulas follows from the construction for every valid N
and seed. It is not a favorable outcome of selecting these four seeds.

All 24 cases passed production and independent serialized-rule SMT checks.
For every UNSAT case the core has exactly K=3; removing any expected core member
from the entire instance makes it SAT, establishing minimality and uniqueness.
See independent-smt.json and test_controlled_v2.py. Legacy v1 pair bytes at
N=3 and N=16 are pinned by pre-change hashes in the self-contained regression.

The original two-family infrastructure plan also reproduced its chain N=48
failure: direct char and Z3 word/char balanced accuracy 0.75, above the unchanged
0.55 threshold. test_original_two_family_chain_smoke_fails_unchanged_leakage_threshold
preserves this regression without a local large bundle.

These are separate demonstrated cues. They do not establish that the exact-text
cue caused the historical TF-IDF score 0.5568627451. Passing these baselines does
not prove the absence of other leakage, and a finite statistical classifier is
not required to score exactly 0.5. Existing word/char TF-IDF and admission remain
unchanged.

Reproduce individual baseline reports from the repository root:

```powershell
.venv/Scripts/python.exe -m scripts.audit_duplicate_cues --plan releases/confirmation-v1/confirmation.plan.json --pattern idem --n 16 --output historical.json
.venv/Scripts/python.exe -m scripts.audit_duplicate_cues --plan configs/development-idem-v2-audit.plan.json --pattern idem --n 3 --output development-N3.json
.venv/Scripts/python.exe -m scripts.audit_duplicate_cues --plan configs/development-idem-v2-audit.plan.json --pattern idem --n 16 --output development-N16.json
.venv/Scripts/python.exe -m scripts.audit_duplicate_cues --plan configs/development-idem-v2-audit.plan.json --pattern idem --n 48 --output development-N48.json
.venv/Scripts/python.exe -m pytest tests/unit/test_controlled_v2.py tests/unit/test_duplicate_cues.py -q
```

The JSON reports preserve plan and cell identity. They contain no model output,
tokenizer/backend assertions or real HTTP evidence.
