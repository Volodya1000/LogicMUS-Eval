"""Duplication features consume only rules; gold labels enter scoring alone."""

import json
import subprocess
import sys

import pytest
from test_controlled_v2 import idem_plan

from logicmus_eval.controlled_generation import generate_cell
from logicmus_eval.duplicate_cues import (
    audit_duplicates,
    canonical_formula,
    duplicate_features,
)
from logicmus_eval.models.rules import (
    FactRule,
    ImpliesRule,
    NoiseRule,
    NumericGTRule,
    NumericLTRule,
)
from logicmus_eval.models.test_case import LogicTestCase


def test_formula_feature_ignores_ids_text_and_literal_role():
    rules = [
        FactRule(
            id="one", text="first wording", variable="p1", predicate="a", polarity=True
        ),
        NoiseRule(
            id="other",
            text="entirely different",
            variable="p1",
            predicate="a",
            polarity=True,
        ),
    ]
    features = duplicate_features(rules)
    assert features.duplicate_text is False
    assert features.duplicate_formula is True
    rules[1].text = rules[0].text
    assert duplicate_features(rules).duplicate_text is True
    rules[1].polarity = False
    assert duplicate_features(rules).duplicate_formula is False


def test_canonical_formula_normalizes_numeric_orientation_and_signed_implications():
    a = NumericGTRule(
        id="one",
        text="a",
        left_var="p1",
        right_var="p2",
        left_predicate="a",
        right_predicate="b",
    )
    b = NumericLTRule(
        id="two",
        text="b",
        left_var="p2",
        right_var="p1",
        left_predicate="b",
        right_predicate="a",
    )
    assert canonical_formula(a) == canonical_formula(b)
    assert canonical_formula(a.model_dump(mode="json")) == canonical_formula(b)
    implication = ImpliesRule(
        id="three",
        text="a",
        antecedent="p1",
        consequent="p2",
        antecedent_predicate="a",
        consequent_predicate="b",
        antecedent_polarity=True,
        consequent_polarity=True,
    )
    negative = implication.model_copy(update={"consequent_polarity": False})
    assert canonical_formula(implication) != canonical_formula(negative)
    assert canonical_formula(negative.model_dump(mode="json")) == canonical_formula(
        negative
    )


def test_legacy_and_v2_baselines_report_confusion_balanced_accuracy_and_sample_size():
    for version in ("controlled-v1", "controlled-v2"):
        plan = idem_plan(version, [42, 44, 424242, 424244], [3, 16, 48])
        cases = [case for cell in plan.cells() for case in generate_cell(plan, cell)]
        result = audit_duplicates(cases)
        assert set(result) == {"exact_text", "canonical_formula"}
        for baseline in result.values():
            assert baseline.cases == 24
            assert baseline.independent_families == 4
            assert (
                sum(sum(row.values()) for row in baseline.confusion_matrix.values())
                == 24
            )
        formulas = result["canonical_formula"]
        assert formulas.confusion_matrix["UNSAT"] == {"SAT": 0, "UNSAT": 12}
        if version == "controlled-v1":
            assert formulas.confusion_matrix["SAT"] == {"SAT": 12, "UNSAT": 0}
            assert formulas.balanced_accuracy == 1.0
        else:
            assert formulas.confusion_matrix["SAT"] == {"SAT": 0, "UNSAT": 12}
            assert formulas.balanced_accuracy == 0.5
            assert result["exact_text"].balanced_accuracy == 0.5


def test_audit_does_not_silently_pool_protocol_versions():
    old, new = idem_plan(), idem_plan("controlled-v2")
    cases = generate_cell(old, old.cells()[0]) + generate_cell(new, new.cells()[0])
    with pytest.raises(ValueError, match="protocol"):
        audit_duplicates(cases)


@pytest.mark.parametrize("version", ["controlled-v1", "controlled-v2"])
def test_saved_jsonl_roundtrip_retains_duplicate_features_and_offline_artifact(
    tmp_path, version
):
    plan = idem_plan(version, [42, 44], [16])
    generated = generate_cell(plan, plan.cells()[0])
    dataset = tmp_path / "cases.jsonl"
    dataset.write_text(
        "\n".join(case.model_dump_json() for case in generated) + "\n", encoding="utf-8"
    )
    restored = [
        LogicTestCase.model_validate_json(line)
        for line in dataset.read_text(encoding="utf-8").splitlines()
    ]
    assert audit_duplicates(restored) == audit_duplicates(generated)
    for original, saved in zip(generated, restored):
        assert duplicate_features(saved.rules) == duplicate_features(original.rules)
        assert [canonical_formula(rule) for rule in saved.rules] == [
            canonical_formula(rule) for rule in original.rules
        ]
    output = tmp_path / "audit.json"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.audit_duplicate_cues",
            "--dataset",
            str(dataset),
            "--output",
            str(output),
        ],
        check=True,
    )
    artifact = json.loads(output.read_text(encoding="utf-8"))
    assert artifact["protocol_versions"] == [version]
    assert artifact["baselines"] == {
        name: value.model_dump(mode="json")
        for name, value in audit_duplicates(generated).items()
    }
    assert artifact["provenance"]["dataset_sha256"]
