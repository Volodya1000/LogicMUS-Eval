"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from pydantic import JsonValue

from logicmus_eval.evaluation.metrics.base import BaseMetric
from logicmus_eval.evaluation.metrics.semantics import contributions, mean_score


class SatAccuracyMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        correct = int(sum(contributions(self.reports, "sat_accuracy")))
        return {
            "sat_accuracy": mean_score(self.reports, "sat_accuracy"),
            "total_evaluated": len(self.reports),
            "correct_sat": correct,
        }
