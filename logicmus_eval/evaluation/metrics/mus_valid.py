"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from pydantic import JsonValue

from logicmus_eval.evaluation.metrics.base import BaseMetric
from logicmus_eval.evaluation.metrics.semantics import contributions, mean_score


class MusValidMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        return {
            "mus_exact_match": mean_score(self.reports, "mus_exact_match"),
            "mus_precision": mean_score(self.reports, "mus_precision"),
            "mus_recall": mean_score(self.reports, "mus_recall"),
            "mus_f1": mean_score(self.reports, "mus_f1"),
            "unsat_evaluated": len(contributions(self.reports, "mus_exact_match")),
        }
