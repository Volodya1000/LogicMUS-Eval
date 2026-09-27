"""Failure classification for LLM evaluation cases."""

import re

from logicmus_eval.enums import FailureTag
from logicmus_eval.evaluation.refusal_patterns import REFUSAL_PATTERNS
from logicmus_eval.models.evaluation import CasePrediction
from logicmus_eval.models.test_case import LogicTestCase

__all__ = ["FailureTag", "classify_failure", "is_refusal"]

_COMPILED_REFUSAL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE) for pattern in REFUSAL_PATTERNS
)


def is_refusal(reasoning: str | None) -> bool:
    """Return True if ``reasoning`` contains a refusal marker.

    Public API so that callers (metrics, pipeline, future consumers) do
    not depend on the internal storage of patterns.
    """
    if not reasoning:
        return False
    return any(pattern.search(reasoning) for pattern in _COMPILED_REFUSAL_PATTERNS)


def classify_failure(
    case: LogicTestCase,
    prediction: CasePrediction | None,
    report_error: str | None,
) -> list[str]:
    """Return failure tags for a single evaluation case."""
    if report_error is not None:
        return [FailureTag.EXEC_ERROR.value]

    tags: list[str] = []

    if prediction is not None and is_refusal(prediction.reasoning):
        tags.append(FailureTag.REFUSAL_NO_FACTS.value)

    if prediction is not None and prediction.is_sat != case.is_satisfiable:
        tags.append(FailureTag.WRONG_SAT.value)

    if (
        case.is_satisfiable is False
        and prediction is not None
        and prediction.is_sat is False
    ):
        expected = set(case.mus_expected)
        predicted = set(prediction.conflict_core)

        if expected - predicted:
            tags.append(FailureTag.WRONG_MUS_MISSING.value)
        if predicted - expected:
            tags.append(FailureTag.WRONG_MUS_EXTRA.value)

    if (
        not tags
        and prediction is not None
        and prediction.is_sat == case.is_satisfiable
        and (
            case.is_satisfiable is True
            or set(prediction.conflict_core) == set(case.mus_expected)
        )
    ):
        tags.append(FailureTag.CORRECT.value)

    if not tags:
        tags.append(FailureTag.UNKNOWN.value)

    return tags
