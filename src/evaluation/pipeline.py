import logging
from collections.abc import Sequence

from src.evaluation.metrics import BaseMetric
from src.evaluation.strategies import BaseEvaluationStrategy
from src.extractor import ExtractorError, StructuredOutputExtractor
from src.models.evaluation import (
    EvaluationCaseReport,
    EvaluationSummary,
    ExtractionMetadata,
)
from src.models.test_case import LogicTestCase

logger = logging.getLogger(__name__)


class EvaluationPipeline:
    def __init__(
        self,
        strategy: BaseEvaluationStrategy,
        extractor: StructuredOutputExtractor,
        metrics: Sequence[BaseMetric],
    ) -> None:
        self.strategy = strategy
        self.extractor = extractor
        self.metrics = metrics

    def run(
        self, dataset: list[LogicTestCase], limit: int | None = None
    ) -> EvaluationSummary:
        for metric in self.metrics:
            metric.reset()

        cases_to_process = dataset[:limit] if limit is not None else dataset
        total = len(cases_to_process)
        details: list[EvaluationCaseReport] = []

        for i, case in enumerate(cases_to_process):
            logger.info("=" * 60)
            logger.info("PROCESSING CASE %d/%d (ID: %s)", i + 1, total, case.case_id)
            logger.info("=" * 60)

            try:
                prediction, metadata = self.strategy.evaluate_case(case, self.extractor)

                is_sat_correct = prediction.is_sat == case.is_satisfiable
                is_mus_correct = False
                if not case.is_satisfiable and prediction.is_sat is False:
                    is_mus_correct = set(case.mus_expected) == set(
                        prediction.conflict_core
                    )

                for metric in self.metrics:
                    metric.update(case, prediction, metadata)

                details.append(
                    EvaluationCaseReport(
                        case_id=case.case_id,
                        mus_size=case.mus_size,
                        expected_sat=case.is_satisfiable,
                        predicted_sat=prediction.is_sat,
                        is_sat_correct=is_sat_correct,
                        expected_mus=case.mus_expected,
                        predicted_mus=prediction.conflict_core,
                        is_mus_correct=is_mus_correct,
                        metadata=metadata,
                        reasoning=prediction.reasoning,
                        generated_code=prediction.generated_code,
                        error=prediction.error,
                    )
                )

            except ExtractorError as e:
                logger.error("Extractor error on case %s: %s", case.case_id, str(e))
                details.append(
                    EvaluationCaseReport(
                        case_id=case.case_id,
                        mus_size=case.mus_size,
                        expected_sat=case.is_satisfiable,
                        predicted_sat=None,
                        is_sat_correct=False,
                        expected_mus=case.mus_expected,
                        predicted_mus=[],
                        is_mus_correct=False,
                        metadata=ExtractionMetadata(),
                        reasoning="",
                        error=str(e),
                    )
                )

        aggregated_metrics = {}
        for metric in self.metrics:
            aggregated_metrics.update(metric.compute())

        return EvaluationSummary(metrics=aggregated_metrics, details=details)
