"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from pydantic import JsonValue

from logicmus_eval.evaluation.metrics.accounting import _ratio
from logicmus_eval.evaluation.metrics.base import BaseMetric


class SatAccuracyMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        correct: int = sum(r.is_sat_correct for r in self.reports)
        return {
            "sat_accuracy": _ratio(correct, len(self.reports)),
            "total_evaluated": len(self.reports),
            "correct_sat": correct,
        }
