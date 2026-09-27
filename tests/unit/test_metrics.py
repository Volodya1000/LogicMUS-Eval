from src.enums import TemplatePackId
from src.evaluation.metrics import (
    InfrastructureErrorRateMetric,
    MusValidMetric,
    RefusalRateMetric,
    SatAccuracyMetric,
    TokenUsageMetric,
    ValidResponseAccuracyMetric,
)
from src.models.evaluation import CasePrediction, ExtractionMetadata
from src.models.test_case import LogicTestCase


def test_sat_accuracy_metric():
    metric = SatAccuracyMetric()
    case = LogicTestCase(
        case_id="c1",
        mus_size=2,
        is_satisfiable=True,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={},
        rules=[],
        mus_expected=[],
    )
    metric.update(case, CasePrediction(is_sat=True), ExtractionMetadata())
    metric.update(case, CasePrediction(is_sat=False), ExtractionMetadata())

    res = metric.compute()
    assert res["sat_accuracy"] == 0.5
    assert res["total_evaluated"] == 2


def test_mus_valid_metric():
    metric = MusValidMetric()
    case = LogicTestCase(
        case_id="c2",
        mus_size=2,
        is_satisfiable=False,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={},
        rules=[],
        mus_expected=["R1", "R2"],
    )
    metric.update(
        case,
        CasePrediction(is_sat=False, conflict_core=["R1", "R2"]),
        ExtractionMetadata(),
    )

    res = metric.compute()
    assert res["mus_exact_match"] == 1.0
    assert res["mus_f1"] == 1.0


def test_token_usage_metric():
    metric = TokenUsageMetric()
    case = LogicTestCase(
        case_id="c3",
        mus_size=1,
        is_satisfiable=True,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={},
        rules=[],
        mus_expected=[],
    )
    metadata = ExtractionMetadata(
        prompt_tokens=100,
        completion_tokens=50,
        thinking_tokens=30,
        total_tokens=150,
    )
    metric.update(case, CasePrediction(), metadata)

    res = metric.compute()
    assert res["total_tokens_consumed"] == 150
    assert res["total_thinking_tokens"] == 30
    assert res["avg_thinking_tokens"] == 30.0


def test_new_failure_metrics():
    refusal_metric = RefusalRateMetric()
    infra_metric = InfrastructureErrorRateMetric()
    valid_metric = ValidResponseAccuracyMetric()

    case = LogicTestCase(
        case_id="c4",
        mus_size=2,
        is_satisfiable=True,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={},
        rules=[],
        mus_expected=[],
    )

    refusal_pred = CasePrediction(reasoning="no explicit initial", is_sat=True)
    error_pred = CasePrediction(is_sat=None, error="boom")
    correct_pred = CasePrediction(is_sat=True)
    wrong_pred = CasePrediction(is_sat=False)

    for metric in (refusal_metric, infra_metric, valid_metric):
        metric.update(case, refusal_pred, ExtractionMetadata())
        metric.update(case, error_pred, ExtractionMetadata())
        metric.update(case, correct_pred, ExtractionMetadata())
        metric.update(case, wrong_pred, ExtractionMetadata())

    refusal_res = refusal_metric.compute()
    assert refusal_res["refusal_count"] == 1
    assert refusal_res["refusal_rate"] == 0.25

    infra_res = infra_metric.compute()
    assert infra_res["infra_error_count"] == 1
    assert infra_res["infrastructure_error_rate"] == 0.25

    valid_res = valid_metric.compute()
    assert valid_res["valid_responses_evaluated"] == 2
    assert valid_res["valid_response_accuracy"] == 0.5
