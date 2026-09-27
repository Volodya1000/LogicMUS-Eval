from src.enums import FailureTag, TemplatePackId
from src.evaluation.diagnostics import classify_failure, is_refusal
from src.models.evaluation import CasePrediction
from src.models.test_case import LogicTestCase


def _case(is_satisfiable: bool, mus_expected: list[str] | None = None) -> LogicTestCase:
    return LogicTestCase(
        case_id="test_case",
        mus_size=2,
        is_satisfiable=is_satisfiable,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={},
        rules=[],
        mus_expected=mus_expected or [],
    )


def test_is_refusal_detects_russian_marker():
    assert is_refusal("нет явных начальных состояний") is True
    assert is_refusal("Невозможно выполнить логический вывод.") is True


def test_is_refusal_returns_false_on_clean_text():
    assert is_refusal("Все правила согласованы, противоречий нет.") is False
    assert is_refusal(None) is False
    assert is_refusal("") is False


def test_classify_exec_error():
    tags = classify_failure(_case(True), None, "boom")
    assert tags == [FailureTag.EXEC_ERROR.value]


def test_classify_refusal_no_facts():
    prediction = CasePrediction(reasoning="no explicit initial", is_sat=True)
    tags = classify_failure(_case(True), prediction, None)
    assert tags == [FailureTag.REFUSAL_NO_FACTS.value]


def test_classify_wrong_sat():
    prediction = CasePrediction(is_sat=False)
    tags = classify_failure(_case(True), prediction, None)
    assert tags == [FailureTag.WRONG_SAT.value]


def test_classify_wrong_mus_missing():
    prediction = CasePrediction(is_sat=False, conflict_core=["R1"])
    tags = classify_failure(_case(False, ["R1", "R2"]), prediction, None)
    assert tags == [FailureTag.WRONG_MUS_MISSING.value]


def test_classify_wrong_mus_extra():
    prediction = CasePrediction(is_sat=False, conflict_core=["R1", "R2"])
    tags = classify_failure(_case(False, ["R1"]), prediction, None)
    assert tags == [FailureTag.WRONG_MUS_EXTRA.value]


def test_classify_correct():
    prediction = CasePrediction(is_sat=True)
    tags = classify_failure(_case(True), prediction, None)
    assert tags == [FailureTag.CORRECT.value]


def test_classify_unknown():
    tags = classify_failure(_case(True), None, None)
    assert tags == [FailureTag.UNKNOWN.value]
