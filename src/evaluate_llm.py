import logging
import os
from pathlib import Path

from src.enums import ManifestFilename
from src.evaluation.metrics import (
    BaseMetric,
    ExecutionTimeMetric,
    MusValidMetric,
    SatAccuracyMetric,
    TokenUsageMetric,
)
from src.evaluation.pipeline import EvaluationPipeline
from src.evaluation.strategies import (
    DirectEvaluationStrategy,
    Z3TranslationEvaluationStrategy,
)
from src.extractor import StructuredOutputExtractor
from src.models.evaluation import EvaluationSummary
from src.storage import FileStorageManager

logger = logging.getLogger(__name__)


def _resolve_dataset_filename(dataset_dir: str) -> str | None:
    preferred = ManifestFilename.DATASET_JSONL.value
    if (Path(dataset_dir) / preferred).exists():
        return preferred

    candidates = list(Path(dataset_dir).glob("*.jsonl"))
    if not candidates:
        return None
    logger.info("Dataset found by glob fallback: %s", candidates[0])
    return candidates[0].name


def _build_metrics() -> list[BaseMetric]:
    return [
        SatAccuracyMetric(),
        MusValidMetric(),
        TokenUsageMetric(),
        ExecutionTimeMetric(),
    ]


def _log_summary(report: EvaluationSummary) -> None:
    logger.info("=" * 50)
    logger.info("EVALUATION METRICS SUMMARY")
    logger.info("=" * 50)
    for k, v in report.metrics.items():
        logger.info("%s: %s", k, v)
    logger.info("=" * 50)


def run_evaluation(
    dataset_dir: str,
    model_name: str,
    strategy_name: str,
    limit: int,
    output_file: str,
) -> None:
    """Library entry point for LLM evaluation (no CLI parsing)."""
    filename = _resolve_dataset_filename(dataset_dir)
    if filename is None:
        logger.error("No .jsonl dataset files found in %s", dataset_dir)
        return

    storage = FileStorageManager(dataset_dir)
    dataset = storage.load_dataset(filename)

    extractor = StructuredOutputExtractor(model_name=model_name)
    strategy = (
        DirectEvaluationStrategy()
        if strategy_name == "direct"
        else Z3TranslationEvaluationStrategy()
    )

    pipeline = EvaluationPipeline(
        strategy=strategy, extractor=extractor, metrics=_build_metrics()
    )

    logger.info(
        "Starting evaluation with strategy: %s on model: %s",
        strategy_name,
        model_name,
    )
    logger.info(
        "Target API Base: %s", os.environ.get("OPENAI_API_BASE", "Default (OpenAI)")
    )

    output_path = Path(dataset_dir) / output_file
    logger.info("Intermediate and final reports will be saved to %s", output_path)

    report = pipeline.run(dataset, limit=limit, output_path=output_path)
    _log_summary(report)

    logger.info("Full report saved to %s", output_path)
