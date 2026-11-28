"""Small self-contained legacy reproduction and signed idem-v2 regressions."""

import json
import random
from itertools import pairwise

import pytest

from logicmus_eval.controlled_generation import generate_cell
from logicmus_eval.enums import TemplatePackId
from logicmus_eval.experiment_plan import ExperimentPlan, content_id
from logicmus_eval.experiment_preparation import prepare_experiment
from logicmus_eval.generation_rendering import render_rule
from logicmus_eval.independent_smt import reference_check, serialized_formula
from logicmus_eval.leakage import calculate_leakage
from logicmus_eval.models.evaluation import ExperimentProvenance
from logicmus_eval.models.rules import FactRule, ImpliesRule, NoiseRule
from logicmus_eval.verifier import verify_case


def idem_plan(version="controlled-v1", seeds=None, ns=None):
    return ExperimentPlan.model_validate(
        {
            "protocol_version": version,
            "purpose": "development",
            "seeds": seeds or [42],
            "pairs_per_seed": 1,
            "series": [
                {
                    "series_id": "idem-regression",
                    "kind": "noise_sweep",
                    "patterns": [{"pattern_id": "idem", "k_values": [3]}],
                    "n_values": ns or [3, 16],
                }
            ],
        }
    )


def correspondence(case):
    return {case.metadata["rule_correspondence"][r.id]: r for r in case.rules}


def test_legacy_idem_defect_is_reproduced_and_v1_bytes_preserved():
    plan = idem_plan()
    hashes = {
        3: "c4b28d2a6218e47d6e69613c4adb10f0dfb154e762d3a2a8b8d21ae3f1509af2",
        16: "2dcd28a6ce02d8ff9af6ab8ac85ec059046df8b1f19e6cc495f899f692348b17",
    }
    for cell in plan.cells():
        cases = generate_cell(plan, cell)
        assert content_id([c.model_dump(mode="json") for c in cases]) == hashes[cell.n]
        sat, unsat = cases
        sat_core, unsat_core = correspondence(sat), correspondence(unsat)
        a, b = (sat_core[f"construction:{i}"] for i in (2, 3))
        assert serialized_formula(a.model_dump(mode="json")) == serialized_formula(
            b.model_dump(mode="json")
        )
        a, b = (unsat_core[f"construction:{i}"] for i in (2, 3))
        assert serialized_formula(a.model_dump(mode="json")) != serialized_formula(
            b.model_dump(mode="json")
        )


@pytest.mark.parametrize("seed", [42, 44, 424242, 424244])
def test_v2_idem_pair_changes_only_fact_preserves_nested_noise_and_signed_text(seed):
    # The pair contract compares construction, presentation and independent SMT.
    # pylint: disable=too-many-locals
    plan = idem_plan("controlled-v2", [seed], [3, 16, 48])
    generated = [generate_cell(plan, cell) for cell in plan.cells()]
    for cases in generated:
        sat, unsat = cases
        a, b = correspondence(sat), correspondence(unsat)
        assert sat.predicate_mapping == unsat.predicate_mapping
        assert list(a) == list(b)
        assert sat.metadata["family_id"] == unsat.metadata["family_id"]
        assert sat.metadata["pair_id"] == unsat.metadata["pair_id"]
        assert [uid for uid in a if a[uid] != b[uid]] == ["construction:1"]
        fact = b["construction:1"]
        sat_fact = a["construction:1"]
        assert isinstance(fact, FactRule) and isinstance(sat_fact, FactRule)
        assert fact.polarity != sat_fact.polarity
        for case in cases:
            core = correspondence(case)
            first, second = (core[f"construction:{i}"] for i in (2, 3))
            assert isinstance(first, ImpliesRule) and isinstance(second, ImpliesRule)
            assert first.antecedent == second.antecedent == fact.variable
            assert (
                first.antecedent_polarity == second.antecedent_polarity == fact.polarity
            )
            assert first.consequent == second.consequent
            assert first.consequent_polarity != second.consequent_polarity
            formulas = [
                serialized_formula(r.model_dump(mode="json")) for r in case.rules
            ]
            assert len(formulas) == len(set(formulas))
            assert len({r.text for r in case.rules}) == len(case.rules)
            # Every implication/literal text is one of the renderings of its
            # actual signed formula, including complemented antecedents.
            for rule in case.rules:
                pool = {
                    render_rule(
                        rule, TemplatePackId(case.template_pack_id), random.Random(i)
                    )
                    for i in range(100)
                }
                if isinstance(rule, FactRule):
                    # Controlled literals intentionally draw the shared NOISE pool.
                    literal = NoiseRule(**rule.model_dump(exclude={"operator_type"}))
                    pool = {
                        render_rule(
                            literal,
                            TemplatePackId(case.template_pack_id),
                            random.Random(i),
                        )
                        for i in range(100)
                    }
                assert rule.text in pool
            result = verify_case(case)
            assert (
                result.is_sat_correct and result.is_mus_valid and result.is_mus_minimal
            )
            assert reference_check(json.loads(case.model_dump_json()))["passed"]
            assert len(case.mus_expected) == (0 if case.is_satisfiable else 3)
            assert (
                ExperimentProvenance.model_validate(case.metadata).protocol_version
                == "controlled-v2"
            )
    for small, large in pairwise(generated):
        for left, right in zip(small, large):
            a, b = correspondence(left), correspondence(right)
            assert list(a) == [uid for uid in b if uid in a]
            assert all(
                r.model_dump(exclude={"id"}) == b[uid].model_dump(exclude={"id"})
                for uid, r in a.items()
            )


def test_v1_v2_identities_and_hashes_are_distinct():
    old, new = idem_plan(), idem_plan("controlled-v2")
    assert old.plan_hash != new.plan_hash
    for old_cell, new_cell in zip(old.cells(), new.cells()):
        assert old_cell.cell_id != new_cell.cell_id
        for a, b in zip(generate_cell(old, old_cell), generate_cell(new, new_cell)):
            assert a.case_id != b.case_id
            assert a.metadata["family_id"] != b.metadata["family_id"]
            assert a.metadata["pair_id"] != b.metadata["pair_id"]
            assert b.metadata["generator_version"] == "controlled-v2"


def test_v2_preparation_records_actual_protocol_and_complete_smt_evidence(tmp_path):
    plan = idem_plan("controlled-v2", [42, 44], [3])
    manifest = prepare_experiment(plan, tmp_path)
    assert manifest.manifest_version == "controlled-v2"
    assert manifest.plan_sha256 == plan.plan_hash
    assert manifest.cells[0].smt_passed
    assert manifest.cells[0].reference_passed
    assert len(manifest.cells[0].smt_checks) == 4
    assert {r["case_id"] for r in manifest.cells[0].smt_checks} == {
        case.case_id for case in generate_cell(plan, plan.cells()[0])
    }


def test_original_two_family_chain_smoke_fails_unchanged_leakage_threshold():
    plan = ExperimentPlan.model_validate(
        {
            "protocol_version": "controlled-v1",
            "purpose": "development",
            "seeds": [424242, 424244],
            "pairs_per_seed": 1,
            "series": [
                {
                    "series_id": "smoke-chain",
                    "kind": "noise_sweep",
                    "patterns": [{"pattern_id": "chain", "k_values": [4]}],
                    "n_values": [48],
                }
            ],
        }
    )
    cases = generate_cell(plan, plan.cells()[0])
    report = calculate_leakage(cases, [4])
    assert report.global_char.mean_balanced_accuracy == 0.75
    assert report.by_input["z3"]["global"]["word_tfidf"].mean_balanced_accuracy == 0.75
    assert not report.acceptance(0.55, [4], ("direct", "z3")).passed
