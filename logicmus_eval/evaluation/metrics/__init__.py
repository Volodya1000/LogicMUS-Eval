"""Public metric API; implementations each have one responsibility."""

from collections.abc import Sequence

from pydantic import JsonValue

from logicmus_eval.evaluation.metrics.accounting import accounting_counts
from logicmus_eval.evaluation.metrics.base import BaseMetric
from logicmus_eval.evaluation.metrics.code_execution_error_rate import (
    CodeExecutionErrorRateMetric,
)
from logicmus_eval.evaluation.metrics.execution_time import ExecutionTimeMetric
from logicmus_eval.evaluation.metrics.infrastructure_error_rate import (
    InfrastructureErrorRateMetric,
)
from logicmus_eval.evaluation.metrics.mus_valid import MusValidMetric
from logicmus_eval.evaluation.metrics.refusal_rate import RefusalRateMetric
from logicmus_eval.evaluation.metrics.response_error_rate import ResponseErrorRateMetric
from logicmus_eval.evaluation.metrics.sat_accuracy import SatAccuracyMetric
from logicmus_eval.evaluation.metrics.token_usage import TokenUsageMetric
from logicmus_eval.evaluation.metrics.valid_response_accuracy import (
    ValidResponseAccuracyMetric,
)
from logicmus_eval.models.evaluation import EvaluationCaseReport

__all__: list[str] = [
    "BaseMetric",
    "CodeExecutionErrorRateMetric",
    "ExecutionTimeMetric",
    "InfrastructureErrorRateMetric",
    "MusValidMetric",
    "RefusalRateMetric",
    "ResponseErrorRateMetric",
    "SatAccuracyMetric",
    "TokenUsageMetric",
    "ValidResponseAccuracyMetric",
    "accounting_counts",
]


def build_metrics() -> list[BaseMetric]:
    return [
        SatAccuracyMetric(),
        MusValidMetric(),
        TokenUsageMetric(),
        ExecutionTimeMetric(),
        RefusalRateMetric(),
        InfrastructureErrorRateMetric(),
        ResponseErrorRateMetric(),
        CodeExecutionErrorRateMetric(),
        ValidResponseAccuracyMetric(),
    ]


def aggregate_outcomes(
    outcomes: Sequence[EvaluationCaseReport], planned: int
) -> dict[str, JsonValue]:
    """One aggregation entry point for saved outcomes and offline consumers."""
    result: dict[str, JsonValue] = {}
    for metric in build_metrics():
        for outcome in outcomes:
            metric.update_report(outcome)
        result.update(metric.compute())
    result.update(accounting_counts(outcomes, planned))
    return result
