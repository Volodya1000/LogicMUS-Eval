"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from pydantic import JsonValue

from logicmus_eval.evaluation.metrics.accounting import _ratio
from logicmus_eval.evaluation.metrics.base import BaseMetric
from logicmus_eval.models.evaluation import EvaluationCaseReport


class ValidResponseAccuracyMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        valid: list[EvaluationCaseReport] = [
            r for r in self.reports if r.valid_response
        ]
        return {
            "valid_response_accuracy": _ratio(
                sum(r.is_sat_correct for r in valid), len(valid)
            ),
            "valid_responses_evaluated": len(valid),
            "coverage": _ratio(len(valid), len(self.reports)),
        }
