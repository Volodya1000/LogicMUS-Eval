"""Finalize case outcomes once, before deriving diagnostics or aggregates."""

import re

from logicmus_eval.enums import EvaluationErrorStage, EvaluationErrorType, FailureTag
from logicmus_eval.evaluation.refusal_patterns import REFUSAL_PATTERNS
from logicmus_eval.models.evaluation import (
    CasePrediction,
    EvaluationCaseReport,
    ExtractionMetadata,
)
from logicmus_eval.models.test_case import LogicTestCase

__all__ = ["FailureTag", "build_case_report", "classify_failure", "is_refusal"]

_COMPILED_REFUSAL_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE) for pattern in REFUSAL_PATTERNS
)


def is_refusal(reasoning: str | None) -> bool:
    """Return whether text contains one of the project's refusal markers."""
    if not reasoning:
        return False
    # Quoted rules, fenced code and negated statements are not refusals.
    text = re.sub(
        r"""```[\s\S]*?```|`[^`\n]*`|"[^"\n]*"|«[^»]*»|“[^”]*”|(?<!\w)'[^'\n]*'(?!\w)""",
        "",
        reasoning,
    )
    for sentence in re.split(
        r"[.!?;\n]|\b(?:but|но|однако)\b", text, flags=re.IGNORECASE
    ):
        if re.search(
            r"\b(?:неверно,? что|неправда,? что|not true that|not the case that)\b",
            sentence,
            re.IGNORECASE,
        ):
            continue
        if any(pattern.search(sentence) for pattern in _COMPILED_REFUSAL_PATTERNS):
            return True
    return False


def _response_error(case: LogicTestCase, prediction: CasePrediction) -> str | None:
    """Check input-relative validity without consulting reference answers."""
    rule_ids = {
        rule["id"] if isinstance(rule, dict) else rule.id for rule in case.rules
    }
    unknown_ids = set(prediction.conflict_core) - rule_ids
    reasons = []
    if unknown_ids:
        reasons.append(f"Unknown rule IDs: {sorted(unknown_ids)}")
    if prediction.is_sat is True and prediction.conflict_core:
        reasons.append("SAT response has a nonempty conflict_core")
    return "; ".join(reasons) or None


# Keep eligibility, correctness and diagnostics together in this finalization step.
# pylint: disable=too-many-locals,too-many-branches
def build_case_report(
    case: LogicTestCase, prediction: CasePrediction, metadata: ExtractionMetadata
) -> EvaluationCaseReport:
    """Single source for eligibility, correctness, scores and diagnostic tags."""
    core = sorted(set(prediction.conflict_core))
    refusal = prediction.refusal or is_refusal(prediction.reasoning)
    error = prediction.error
    error_type = prediction.error_type
    error_stage = prediction.error_stage
    if error is not None or not prediction.execution_success:
        error = error or "Execution failed without an error message"
        error_type = error_type or EvaluationErrorType.EXEC_ERROR
        error_stage = error_stage or EvaluationErrorStage.EXECUTION
    elif error_type is not None:
        error = f"Response failed: {error_type}"
    else:
        error = _response_error(case, prediction)
        if error is not None:
            error_type, error_stage = (
                EvaluationErrorType.INVALID_RESPONSE,
                EvaluationErrorStage.RESPONSE_VALIDATION,
            )
        elif prediction.is_sat is None and not refusal:
            error = "Missing SAT/UNSAT verdict"
            error_type, error_stage = (
                EvaluationErrorType.MISSING_ANSWER,
                EvaluationErrorStage.RESPONSE_VALIDATION,
            )

    valid = error is None and not refusal and prediction.is_sat is not None
    sat_correct = valid and prediction.is_sat == case.is_satisfiable
    mus_correct = False
    precision = recall = f1 = None
    if not case.is_satisfiable:
        precision = recall = f1 = 0.0
        if valid and prediction.is_sat is False:
            expected, predicted = set(case.mus_expected), set(core)
            mus_correct = expected == predicted
            overlap = len(expected & predicted)
            precision = overlap / len(predicted) if predicted else 0.0
            recall = overlap / len(expected) if expected else 0.0
            f1 = (
                2 * overlap / (len(expected) + len(predicted))
                if expected or predicted
                else 0.0
            )

    tags: list[str] = []
    if error_type is not None:
        tags.append(error_type.value)
    if refusal:
        tags.append(FailureTag.REFUSAL_NO_FACTS.value)
    if valid:
        if not sat_correct:
            tags.append(FailureTag.WRONG_SAT.value)
        elif not case.is_satisfiable:
            if set(case.mus_expected) - set(core):
                tags.append(FailureTag.WRONG_MUS_MISSING.value)
            if set(core) - set(case.mus_expected):
                tags.append(FailureTag.WRONG_MUS_EXTRA.value)
        if not tags:
            tags.append(FailureTag.CORRECT.value)

    return EvaluationCaseReport(
        case_id=case.case_id,
        mus_size=case.mus_size,
        expected_sat=case.is_satisfiable,
        expected_mus=case.mus_expected,
        predicted_sat=prediction.is_sat,
        predicted_mus=core,
        is_sat_correct=sat_correct,
        is_mus_correct=mus_correct,
        valid_response=valid,
        refusal=refusal,
        mus_precision=precision,
        mus_recall=recall,
        mus_f1=f1,
        metadata=metadata,
        reasoning=prediction.reasoning,
        generated_code=prediction.generated_code,
        raw_response=prediction.raw_response,
        error=error,
        error_type=error_type,
        error_stage=error_stage,
        error_category=error_type.category if error_type is not None else None,
        failure_tags=tags or [FailureTag.UNKNOWN.value],
    )


def classify_failure(
    case: LogicTestCase,
    prediction: CasePrediction | None,
    report_error: str | None,
) -> list[str]:
    """Compatibility helper; new callers consume the finalized report's tags."""
    if prediction is None and report_error is None:
        return [FailureTag.UNKNOWN.value]
    prediction = (prediction or CasePrediction()).model_copy()
    if report_error is not None:
        prediction.error = report_error
    return build_case_report(case, prediction, ExtractionMetadata()).failure_tags
