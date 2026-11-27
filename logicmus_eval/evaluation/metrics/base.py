"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from pydantic import JsonValue

from logicmus_eval.evaluation.diagnostics import build_case_report
from logicmus_eval.models.evaluation import (
    CasePrediction,
    EvaluationCaseReport,
    ExtractionMetadata,
)
from logicmus_eval.models.test_case import LogicTestCase


class BaseMetric(ABC):
    def __init__(self) -> None:
        self.reports: list[EvaluationCaseReport] = []

    def update(
        self,
        case: LogicTestCase,
        prediction: CasePrediction,
        metadata: ExtractionMetadata,
    ) -> None:
        """Retain standalone callers; the pipeline finalizes the outcome only once."""
        self.update_report(build_case_report(case, prediction, metadata))

    def update_report(self, report: EvaluationCaseReport) -> None:
        self.reports.append(report)

    @abstractmethod
    def compute(self) -> Mapping[str, JsonValue]:
        pass

    def reset(self) -> None:
        self.reports.clear()
