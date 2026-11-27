"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from pydantic import JsonValue

from logicmus_eval.enums import EvaluationErrorCategory
from logicmus_eval.evaluation.metrics.accounting import _ratio
from logicmus_eval.evaluation.metrics.base import BaseMetric


class InfrastructureErrorRateMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        count: int = sum(
            r.error_category is EvaluationErrorCategory.API for r in self.reports
        )
        return {
            "infra_error_count": count,
            "infrastructure_error_rate": _ratio(count, len(self.reports)),
        }
