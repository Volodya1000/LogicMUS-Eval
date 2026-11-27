"""PR #3 per-observation semantics shared by aggregates and statistical consumers."""

from collections.abc import Sequence
from typing import Literal, assert_never

from logicmus_eval.models.evaluation import EvaluationCaseReport

MetricName = Literal[
    "mus_exact_match",
    "mus_precision",
    "mus_recall",
    "mus_f1",
    "sat_accuracy",
    "coverage",
    "valid_response_accuracy",
]


def observation(report: EvaluationCaseReport, metric: MetricName) -> float | None:
    """None excludes a row; 0 includes a failed/null-scored row in its denominator."""
    value: float | None
    match metric:
        case "mus_exact_match" | "mus_precision" | "mus_recall" | "mus_f1":
            if report.expected_sat:
                return None
            match metric:
                case "mus_exact_match":
                    value = float(report.is_mus_correct)
                case "mus_precision":
                    value = report.mus_precision or 0.0
                case "mus_recall":
                    value = report.mus_recall or 0.0
                case "mus_f1":
                    value = report.mus_f1 or 0.0
                case _:
                    assert_never(metric)
        case "sat_accuracy":
            value = float(report.is_sat_correct)
        case "coverage":
            value = float(bool(report.valid_response))
        case "valid_response_accuracy":
            value = float(report.is_sat_correct) if report.valid_response else None
        case _:
            assert_never(metric)
    return value


def contributions(
    reports: Sequence[EvaluationCaseReport], metric: MetricName
) -> list[float]:
    return [
        value
        for report in reports
        if (value := observation(report, metric)) is not None
    ]


def mean_score(
    reports: Sequence[EvaluationCaseReport], metric: MetricName
) -> float | None:
    values = contributions(reports, metric)
    return sum(values) / len(values) if values else None
