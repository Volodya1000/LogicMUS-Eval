"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from pydantic import JsonValue

from logicmus_eval.evaluation.metrics.base import BaseMetric
from logicmus_eval.evaluation.metrics.semantics import contributions, mean_score


class ValidResponseAccuracyMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        return {
            "valid_response_accuracy": mean_score(
                self.reports, "valid_response_accuracy"
            ),
            "valid_responses_evaluated": len(
                contributions(self.reports, "valid_response_accuracy")
            ),
            "coverage": mean_score(self.reports, "coverage"),
        }
