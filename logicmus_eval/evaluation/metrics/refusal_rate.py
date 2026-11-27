"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from pydantic import JsonValue

from logicmus_eval.evaluation.metrics.accounting import _ratio
from logicmus_eval.evaluation.metrics.base import BaseMetric


class RefusalRateMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        count: int = sum(r.refusal is True for r in self.reports)
        return {
            "refusal_count": count,
            "refusal_rate": _ratio(count, len(self.reports)),
        }
