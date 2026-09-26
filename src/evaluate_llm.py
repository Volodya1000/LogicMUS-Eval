import argparse
import json
import logging
import os
from pathlib import Path

from src.enums import ManifestFilename
from src.evaluation.metrics import (
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
from src.models.test_case import LogicTestCase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
)

logger = logging.getLogger(__name__)


def load_dataset(filepath: Path) -> list[LogicTestCase]:
    dataset = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            dataset.append(LogicTestCase.model_validate(data))
    return dataset


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate LLM on LogicMUS-Eval dataset."
    )
    parser.add_argument("--dataset-dir", type=str, default="data/generated_cases")
    parser.add_argument(
        "--model-name", type=str, default="openai/qwen2.5-coder-14b-instruct"
    )
    parser.add_argument(
        "--strategy", type=str, choices=["direct", "z3"], default="direct"
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output-file", type=str, default="evaluation_results.json")
    args = parser.parse_args()

    dataset_path = Path(args.dataset_dir) / ManifestFilename.DATASET_JSONL.value
    if not dataset_path.exists():
        candidates = list(Path(args.dataset_dir).glob("*.jsonl"))
        if candidates:
            dataset_path = candidates[0]
            logger.info("Dataset found by glob fallback: %s", dataset_path)
        else:
            logger.error("No .jsonl dataset files found in %s", args.dataset_dir)
            return

    dataset = load_dataset(dataset_path)
    extractor = StructuredOutputExtractor(model_name=args.model_name)

    strategy = (
        DirectEvaluationStrategy()
        if args.strategy == "direct"
        else Z3TranslationEvaluationStrategy()
    )

    metrics = [
        SatAccuracyMetric(),
        MusValidMetric(),
        TokenUsageMetric(),
        ExecutionTimeMetric(),
    ]

    pipeline = EvaluationPipeline(
        strategy=strategy, extractor=extractor, metrics=metrics
    )

    logger.info(
        "Starting evaluation with strategy: %s on model: %s",
        args.strategy,
        args.model_name,
    )
    logger.info(
        "Target API Base: %s", os.environ.get("OPENAI_API_BASE", "Default (OpenAI)")
    )

    report = pipeline.run(dataset, limit=args.limit)

    logger.info("=" * 50)
    logger.info("EVALUATION METRICS SUMMARY")
    logger.info("=" * 50)
    for k, v in report.metrics.items():
        logger.info("%s: %s", k, v)
    logger.info("=" * 50)

    output_path = Path(args.dataset_dir) / args.output_file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report.model_dump_json(indent=2))

    logger.info("Full report saved to %s", output_path)


if __name__ == "__main__":
    main()
