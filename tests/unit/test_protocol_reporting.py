import pytest

from logicmus_eval.evaluation.diagnostics import build_case_report
from logicmus_eval.evaluation.strategies import (
    DirectEvaluationStrategy,
    Z3TranslationEvaluationStrategy,
)
from logicmus_eval.generator import BenchmarkGenerator
from logicmus_eval.models.evaluation import (
    CasePrediction,
    EvaluationSummary,
    ExtractionMetadata,
)
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.patterns.coverage import CoveragePatternStrategy
from logicmus_eval.patterns.idem import IdemPatternStrategy
from logicmus_eval.patterns.math import MathPatternStrategy
from logicmus_eval.patterns.merge import MergePatternStrategy


@pytest.fixture(name="experiment_metadata")
def fixture_experiment_metadata() -> dict[str, str | int]:
    return {
        "protocol_version": "controlled-v1",
        "cell_id": "private-cell",
        "family_id": "private-family",
        "pair_id": "private-pair",
        "pattern_id": "coverage",
        "purpose": "development",
        "series_id": "private-series",
        "series_kind": "topology_panel",
        "seed": 42,
        "pair_index": 0,
        "total_rules": 4,
        "construction_rule_count": 3,
        "independent_noise_count": 1,
        "case_uid": "private-case-uid",
    }


@pytest.mark.parametrize(
    "pattern,k",
    [
        (CoveragePatternStrategy, 3),
        (IdemPatternStrategy, 3),
        (MergePatternStrategy, 4),
        (MathPatternStrategy, 3),
    ],
)
@pytest.mark.parametrize(
    "strategy", [DirectEvaluationStrategy, Z3TranslationEvaluationStrategy]
)
def test_prompt_supports_general_constraints_and_keeps_input_shape(
    strategy, pattern, k, experiment_metadata
):
    _, case = BenchmarkGenerator(
        pattern(), total_rules=k + 1, pack_id=pattern.forced_pack_id
    ).generate_pair(k, 0)
    request = strategy().build_prompt(case)

    if strategy is DirectEvaluationStrategy:
        assert "Выпиши все FACT" not in request
        assert "Проверь терминальное правило" not in request
        assert '"is_sat":' in request and '"conflict_core":' in request
        assert '"python_z3_code":' not in request
    else:
        assert '"python_z3_code":' in request
        assert '"is_sat":' not in request and '"conflict_core":' not in request
        assert "solver.assert_and_track" in request
        assert "Bool('" in request
        assert ("Real('" in request) is (pattern is MathPatternStrategy)

    assert "ограничения, которые должны выполняться одновременно" in request
    assert "материальная импликация" in request
    assert "включающее «или»" in request
    assert "Отсутствие утверждения не означает ложность" in request
    assert "булевы выражения и числовые сравнения" in request
    assert "явных фактов или отдельного терминального правила не требуется" in request
    assert '"reasoning":' in request

    rules = request.split("<RULES>\n", 1)[1].split("</RULES>", 1)[0].splitlines()
    assert [line.split(" | ", 1)[0] for line in rules if line] == [
        f"ID: R{number}" for number in range(1, k + 2)
    ]
    assert all(" | Var: " in line and " | Rule: " in line for line in rules if line)

    controlled = case.model_copy(
        update={
            "case_id": "private-case",
            "mus_expected": ["private-oracle-core"],
            "metadata": {
                **experiment_metadata,
                "rule_correspondence": {"private-construction-rule": "R1"},
                "independent_noise_ids": ["private-noise-rule"],
            },
        }
    )
    reloaded = LogicTestCase.model_validate_json(controlled.model_dump_json())
    assert strategy().build_prompt(reloaded) == request


def test_controlled_report_preserves_experiment_provenance(experiment_metadata):
    sat, _ = BenchmarkGenerator(CoveragePatternStrategy(), total_rules=4).generate_pair(
        3, 0
    )
    sat.metadata = {**experiment_metadata, "rule_correspondence": {"internal": "R1"}}
    detail = build_case_report(sat, CasePrediction(is_sat=True), ExtractionMetadata())

    summary = EvaluationSummary(details=[detail], metrics={})
    restored = EvaluationSummary.model_validate_json(summary.model_dump_json())
    assert restored.details[0].model_dump().get("experiment") == experiment_metadata


def test_legacy_report_leaves_experiment_provenance_unknown():
    sat, _ = BenchmarkGenerator(CoveragePatternStrategy()).generate_pair(3, 0)
    detail = build_case_report(sat, CasePrediction(is_sat=True), ExtractionMetadata())

    assert detail.model_dump().get("experiment") is None
    legacy = EvaluationSummary.model_validate(
        {"metrics": {}, "details": [detail.model_dump(exclude={"experiment"})]}
    )
    assert legacy.details[0].experiment is None
    assert legacy.report_schema_version is None


@pytest.mark.parametrize("invalid_metadata", [{"pair_index": "0"}, {"case_uid": None}])
def test_incomplete_or_malformed_provenance_stays_unknown(
    experiment_metadata, invalid_metadata
):
    sat, _ = BenchmarkGenerator(CoveragePatternStrategy()).generate_pair(3, 0)
    sat.metadata = {**experiment_metadata, **invalid_metadata}
    detail = build_case_report(sat, CasePrediction(is_sat=True), ExtractionMetadata())

    assert detail.experiment is None
