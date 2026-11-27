"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from pydantic import JsonValue

from logicmus_eval.evaluation.metrics.accounting import _ratio
from logicmus_eval.evaluation.metrics.base import BaseMetric
from logicmus_eval.models.evaluation import EvaluationCaseReport


class MusValidMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        unsat: list[EvaluationCaseReport] = [
            r for r in self.reports if not r.expected_sat
        ]
        return {
            "mus_exact_match": _ratio(sum(r.is_mus_correct for r in unsat), len(unsat)),
            "mus_precision": _ratio(
                sum(r.mus_precision or 0.0 for r in unsat), len(unsat)
            ),
            "mus_recall": _ratio(sum(r.mus_recall or 0.0 for r in unsat), len(unsat)),
            "mus_f1": _ratio(sum(r.mus_f1 or 0.0 for r in unsat), len(unsat)),
            "unsat_evaluated": len(unsat),
        }
