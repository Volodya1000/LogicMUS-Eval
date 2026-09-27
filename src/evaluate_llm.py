import hashlib
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from src.enums import ManifestFilename
from src.evaluation.metrics import (
    BaseMetric,
    ExecutionTimeMetric,
    InfrastructureErrorRateMetric,
    MusValidMetric,
    RefusalRateMetric,
    SatAccuracyMetric,
    TokenUsageMetric,
    ValidResponseAccuracyMetric,
)
from src.evaluation.pipeline import EvaluationPipeline
from src.evaluation.strategies import (
    DIRECT_PROMPT_TEMPLATE,
    Z3_PROMPT_TEMPLATE,
    DirectEvaluationStrategy,
    Z3TranslationEvaluationStrategy,
)
from src.extractor import StructuredOutputExtractor
from src.hashing import compute_file_sha256
from src.models.evaluation import EvaluationSummary, RunInfo
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
        RefusalRateMetric(),
        InfrastructureErrorRateMetric(),
        ValidResponseAccuracyMetric(),
    ]


def _log_summary(report: EvaluationSummary) -> None:
    logger.info("=" * 50)
    logger.info("EVALUATION METRICS SUMMARY")
    logger.info("=" * 50)
    for k, v in report.metrics.items():
        logger.info("%s: %s", k, v)
    logger.info("=" * 50)


def _get_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path.cwd(),
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


# pylint: disable=too-many-locals
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

    dataset_path = Path(dataset_dir) / filename
    started_at = datetime.now(UTC)
    dataset_sha256 = compute_file_sha256(dataset_path)
    prompt_template_hash = hashlib.sha256(
        (DIRECT_PROMPT_TEMPLATE + Z3_PROMPT_TEMPLATE).encode("utf-8")
    ).hexdigest()
    git_commit = _get_git_commit()

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
    logger.info("Final report will be saved to %s", output_path)

    report = pipeline.run(dataset, limit=limit)
    finished_at = datetime.now(UTC)

    run_info = RunInfo(
        model_name=model_name,
        strategy=strategy_name,
        dataset_filename=filename,
        dataset_sha256=dataset_sha256,
        prompt_template_hash=prompt_template_hash,
        git_commit=git_commit,
        started_at=started_at,
        finished_at=finished_at,
        limit=limit,
        total_cases_processed=len(report.details),
    )
    report.run_info = run_info
    output_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    logger.info("RunInfo:\n%s", run_info.model_dump_json(indent=2))
    _log_summary(report)
    logger.info("Full report saved to %s", output_path)
