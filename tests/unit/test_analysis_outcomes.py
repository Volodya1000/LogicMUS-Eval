"""Known finalized scores and independent family counts, never list-based scoring."""

import pytest
from pydantic import ValidationError

from logicmus_eval.analysis.plan import AnalysisPlan
from logicmus_eval.analysis.tables import error_bucket, metrics_for
from logicmus_eval.enums import EvaluationErrorType
from logicmus_eval.evaluation.diagnostics import build_case_report
from logicmus_eval.models.evaluation import CasePrediction, ExtractionMetadata
from logicmus_eval.models.test_case import LogicTestCase


def outcome(index, prediction):
    case = LogicTestCase(
        case_id=f"local-{index}",
        mus_size=2,
        is_satisfiable=False,
        template_pack_id="pack_00",
        predicate_mapping={},
        rules=[{"id": "a"}, {"id": "b"}],
        mus_expected=["a", "b"],
    )
    return build_case_report(case, prediction, ExtractionMetadata())


def test_errors_refusals_and_failed_execution_keep_unsat_denominator():
    correct = CasePrediction(is_sat=False, conflict_core=["a", "b"])
    predictions = [
        correct,
        correct.model_copy(update={"execution_success": False}),
        correct.model_copy(update={"refusal": True}),
        CasePrediction(is_sat=True),
        correct.model_copy(
            update={"error_type": EvaluationErrorType.GENERATION_TRUNCATED}
        ),
    ]
    outcomes = [outcome(i, prediction) for i, prediction in enumerate(predictions)]
    result = metrics_for(outcomes, 5)
    assert result["mus_exact_match"] == result["mus_f1"] == 0.2
    assert result["sat_accuracy"] == 0.2
    assert result["coverage"] == 0.4
    assert result["unsat_evaluated"] == 5
    assert result["total_tokens_consumed"] is None
    assert result["total_execution_seconds"] is None
    assert result["total_llm_seconds"] is None
    assert result["token_accounting_complete"] is False
    assert [error_bucket(r) for r in outcomes] == [
        "correct",
        "error:exec_error",
        "refusal",
        "wrong_sat",
        "error:generation_truncated",
    ]
    unknown = outcomes[0].model_copy(
        update={"valid_response": None, "failure_tags": []}
    )
    assert error_bucket(unknown) == "invalid_or_unknown"


def test_plan_rejects_unknowns_unseeded_and_implicit_weight_requests():
    with pytest.raises(ValidationError):
        AnalysisPlan.model_validate({"analysis_version": "controlled-analysis-v1"})


def test_plan_rejects_empty_group_selection():
    with pytest.raises(ValidationError):
        AnalysisPlan.model_validate(
            {
                "analysis_version": "controlled-analysis-v1",
                "purpose": "development",
                "groups": [{"name": "empty", "run_ids": ["run"], "model_ids": []}],
                "intervals": {"seed": 1},
            }
        )
