"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from pydantic import JsonValue

from logicmus_eval.enums import EvaluationErrorCategory
from logicmus_eval.evaluation.metrics.accounting import _ratio
from logicmus_eval.evaluation.metrics.base import BaseMetric


class ResponseErrorRateMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        count: int = sum(
            r.error_category is EvaluationErrorCategory.RESPONSE for r in self.reports
        )
        return {
            "response_error_count": count,
            "response_error_rate": _ratio(count, len(self.reports)),
        }
