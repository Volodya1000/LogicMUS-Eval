import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from pydantic import JsonValue

from logicmus_eval.enums import EvaluationErrorType, EvaluationStatus
from logicmus_eval.evaluation.diagnostics import build_case_report
from logicmus_eval.evaluation.metrics import BaseMetric, accounting_counts
from logicmus_eval.evaluation.strategies import BaseEvaluationStrategy
from logicmus_eval.extractor import ExtractorError, StructuredOutputExtractor
from logicmus_eval.models.evaluation import (
    METRIC_DEFINITIONS_VERSION,
    REPORT_SCHEMA_VERSION,
    CasePrediction,
    EvaluationCaseReport,
    EvaluationSummary,
    RunInfo,
)
from logicmus_eval.models.test_case import LogicTestCase

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

    def _summary(
        self,
        details: list[EvaluationCaseReport],
        planned: int,
        completed: bool,
        run_info: RunInfo | None,
    ) -> EvaluationSummary:
        aggregated: dict[str, JsonValue] = {}
        for metric in self.metrics:
            aggregated.update(metric.compute())
        aggregated.update(accounting_counts(details, planned))
        if run_info is not None:
            run_info.total_cases_processed = len(details)
            run_info.finished_at = datetime.now(UTC) if completed else None
        return EvaluationSummary(
            metrics=aggregated,
            details=details,
            run_info=run_info,
            report_schema_version=REPORT_SCHEMA_VERSION,
            metric_definitions_version=METRIC_DEFINITIONS_VERSION,
            status=EvaluationStatus.COMPLETED
            if completed
            else EvaluationStatus.RUNNING,
        )

    # pylint: disable=too-many-locals
    def run(
        self,
        dataset: list[LogicTestCase],
        limit: int | None = None,
        output_path: Path | None = None,
        run_info: RunInfo | None = None,
        save_each_case: bool = True,
    ) -> EvaluationSummary:
        if limit is not None and limit < 0:
            raise ValueError("limit must be nonnegative")
        for metric in self.metrics:
            metric.reset()
        if run_info is not None:
            run_info.finished_at = None
        cases = dataset[:limit] if limit is not None else dataset
        details: list[EvaluationCaseReport] = []

        def snapshot(completed: bool = False) -> EvaluationSummary:
            report = self._summary(details, len(cases), completed, run_info)
            if output_path is not None:
                output_path.write_text(
                    report.model_dump_json(indent=2), encoding="utf-8"
                )
            return report

        snapshot()
        completed = False
        try:
            for index, case in enumerate(cases):
                logger.info(
                    "PROCESSING CASE %d/%d (ID: %s)",
                    index + 1,
                    len(cases),
                    case.case_id,
                )
                case_started = perf_counter()
                try:
                    prediction, metadata = self.strategy.evaluate_case(
                        case, self.extractor
                    )
                except ExtractorError as exc:
                    logger.error("Request failed on case %s: %s", case.case_id, exc)
                    refusal = exc.error_type is EvaluationErrorType.REFUSAL
                    prediction = CasePrediction(
                        error=None if refusal else str(exc),
                        error_type=None if refusal else exc.error_type,
                        error_stage=None if refusal else exc.stage,
                        raw_response=exc.raw_response,
                        refusal=refusal or exc.refusal,
                        reasoning=str(exc) if refusal else "",
                    )
                    metadata = exc.metadata
                outcome = build_case_report(case, prediction, metadata)
                metadata.case_latency_seconds = perf_counter() - case_started
                for metric in self.metrics:
                    metric.update_report(outcome)
                details.append(outcome)
                if output_path is not None and save_each_case:
                    snapshot()
            completed = True
        finally:
            # Flush without converting unexpected exceptions or interrupts.
            # CLI disables per-case snapshots to avoid quadratic serialization.
            report = snapshot(completed=completed)

        return report
