"""Contracts that distinguish controlled-v1 from legacy same-seed generation."""

import json

import pytest

from logicmus_eval.controlled_generation import generate_cell, present_rules
from logicmus_eval.enums import TemplatePackId
from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.independent_smt import reference_check
from logicmus_eval.models.rules import FactRule, NoiseRule, TerminalRule
from logicmus_eval.verifier import verify_case


def plan_for(pattern="chain", ks=None, ns=None, kind="noise_sweep", **updates):
    payload = {
        "protocol_version": "controlled-v1",
        "purpose": "development",
        "seeds": [42],
        "pairs_per_seed": 2,
        "series": [
            {
                "series_id": "main",
                "kind": kind,
                "patterns": [{"pattern_id": pattern, "k_values": ks or [3]}],
                "n_values": ns or [5, 9],
            }
        ],
    }
    payload.update(updates)
    return ExperimentPlan.model_validate(payload)


def stable_rules(case):
    return {
        case.metadata["rule_correspondence"][r.id]: r.model_dump(exclude={"id"})
        for r in case.rules
    }


@pytest.mark.parametrize(
    "pattern,k,n",
    [
        ("chain", 4, 4),
        ("direct", 2, 2),
        ("coverage", 3, 3),
        ("fork", 3, 4),
        ("idem", 3, 3),
        ("merge", 4, 4),
        ("math", 4, 4),
    ],
)
def test_nested_noise_preserves_full_construction_pair_edit_and_order(pattern, k, n):
    # pylint: disable=too-many-locals
    plan = plan_for(pattern, [k], [n, n + 5])
    small, large = [generate_cell(plan, c) for c in plan.cells()]
    for a, b in zip(small, large):
        ra, rb = stable_rules(a), stable_rules(b)
        assert ra.items() <= rb.items()
        old = list(a.metadata["rule_correspondence"].values())
        new = list(b.metadata["rule_correspondence"].values())
        assert old == [uid for uid in new if uid in old]
        assert a.metadata["family_id"] == b.metadata["family_id"]
        assert a.metadata["pair_id"] != b.metadata["pair_id"]
        assert a.metadata["construction_rule_count"] == n
        assert b.metadata["independent_noise_count"] == 5
        core_a = {a.metadata["rule_correspondence"][rid] for rid in a.mus_expected}
        core_b = {b.metadata["rule_correspondence"][rid] for rid in b.mus_expected}
        assert core_a == core_b
        result = verify_case(b)
        assert result.is_sat_correct and result.is_mus_valid and result.is_mus_minimal
        assert reference_check(json.loads(b.model_dump_json()))["passed"]
    for sat, unsat in zip(large[::2], large[1::2]):
        a, b = stable_rules(sat), stable_rules(unsat)
        assert [uid for uid in a if a[uid] != b[uid]] == [f"construction:{n}"]
        assert sat.metadata["family_id"] == unsat.metadata["family_id"]
        assert sat.metadata["pair_id"] == unsat.metadata["pair_id"]


def test_plan_reordering_and_extension_preserve_tasks():
    plan = plan_for()
    original = {
        c.cell_id: [x.model_dump() for x in generate_cell(plan, c)]
        for c in plan.cells()
    }
    payload = plan.model_dump()
    payload["series"][0]["n_values"] = [12, 9, 5]
    payload["series"].insert(
        0,
        {
            "series_id": "extra",
            "kind": "k_sweep",
            "n_values": [10],
            "patterns": [{"pattern_id": "math", "k_values": [2, 4]}],
        },
    )
    extended = ExperimentPlan.model_validate(payload)
    for cell in extended.cells():
        if cell.cell_id in original:
            assert original[cell.cell_id] == [
                x.model_dump() for x in generate_cell(extended, cell)
            ]
    reordered = plan.model_copy(deep=True)
    reordered.series[0].n_values.reverse()
    assert reordered.plan_hash == plan.plan_hash


@pytest.mark.parametrize(
    "pattern,ks,ns,kind,match",
    [
        ("coverage", [3, 4], [8], "k_sweep", "scalable"),
        ("chain", [2, 3], [8], "k_sweep", "does not support K=2"),
        ("fork", [3], [3, 8], "noise_sweep", "construction"),
        ("chain", [3], [5, 5000], "noise_sweep", "predicate pool"),
        ("chain", [3, 4], [8, 9], "k_sweep", "one N"),
        ("coverage", [3], [8, 9], "topology_panel", "one N"),
    ],
)
def test_invalid_entire_plan_rejected(pattern, ks, ns, kind, match):
    with pytest.raises(ValueError, match=match):
        plan_for(pattern, ks, ns, kind)


def test_k_sweep_never_substitutes_topologies():
    plan = plan_for("chain", [3, 4, 6], [10], "k_sweep")
    assert {c.pattern_id for c in plan.cells()} == {"chain"}
    assert {
        x.metadata["pattern_id"] for c in plan.cells() for x in generate_cell(plan, c)
    } == {"chain"}


def test_purpose_partition_prevents_cross_plan_family_leakage():
    dev = plan_for()
    with pytest.raises(ValueError, match="odd seeds"):
        plan_for(purpose="confirmation")
    confirmation = plan_for(purpose="confirmation", seeds=[43])

    def families(p):
        return {x.metadata["family_id"] for c in p.cells() for x in generate_cell(p, c)}

    assert families(dev).isdisjoint(families(confirmation))


def test_case_ids_unique_across_datasets_and_pair_indices():
    plan = plan_for(seeds=[42, 44])
    cases = [x for c in plan.cells() for x in generate_cell(plan, c)]
    assert len({x.case_id for x in cases}) == len(cases)
    assert all(x.case_id == x.metadata["case_uid"] for x in cases)


@pytest.mark.parametrize("seed", range(10))
def test_literal_wording_cannot_identify_construction_or_noise_role(seed):
    texts = []
    for cls in (FactRule, TerminalRule, NoiseRule):
        rule = cls(id="R1", text="", variable="p1", predicate="альфа", polarity=True)
        rendered = present_rules([rule], {"p1": "альфа"}, TemplatePackId.PACK_00, seed)
        texts.append(rendered[0].text)
    assert len(set(texts)) == 1
