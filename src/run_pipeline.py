import logging
import platform
from dataclasses import dataclass

import numpy as np
import sklearn  # type: ignore
import z3  # type: ignore
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
from sklearn.linear_model import LogisticRegression  # type: ignore
from sklearn.metrics import f1_score  # type: ignore
from sklearn.model_selection import StratifiedGroupKFold  # type: ignore

from src.enums import AnalyzerType, ManifestFilename, MetricType
from src.generator import BenchmarkGenerator
from src.hashing import compute_file_sha256, compute_source_bundle_hash
from src.models.manifests import (
    ArtifactsManifest,
    BenchmarkManifest,
    EnvironmentManifest,
    LeakageMetricsGlobal,
    ParametersManifest,
    TfidfMetrics,
    ValidationResultsManifest,
)
from src.models.pipeline import DatasetValidationMetrics, LeakageReport
from src.models.test_case import LogicTestCase
from src.patterns.base import BasePatternStrategy
from src.patterns.chain import ChainPatternStrategy
from src.patterns.coverage import CoveragePatternStrategy
from src.patterns.direct import DirectPatternStrategy
from src.patterns.fork import ForkPatternStrategy
from src.patterns.idem import IdemPatternStrategy
from src.patterns.math import MathPatternStrategy
from src.patterns.merge import MergePatternStrategy
from src.storage import FileStorageManager, StorageProtocol
from src.verifier import verify_case

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationConfig:
    mus_sizes: list[int]
    pairs_per_group: int
    total_rules: int
    base_seed: int
    output_dir: str


# Registry is a plain list of classes. Each strategy self-describes its
# ``name``, ``min_mus_size`` and ``forced_pack_id`` via ClassVar attributes.
STRATEGY_REGISTRY: list[type[BasePatternStrategy]] = [
    ChainPatternStrategy,
    CoveragePatternStrategy,
    DirectPatternStrategy,
    ForkPatternStrategy,
    IdemPatternStrategy,
    MergePatternStrategy,
    MathPatternStrategy,
]


def _eligible_strategies(mus_size: int) -> list[type[BasePatternStrategy]]:
    eligible = [cls for cls in STRATEGY_REGISTRY if cls.supports(mus_size)]
    if not eligible:
        raise ValueError(
            f"No strategy supports mus_size={mus_size}. "
            f"Registry: {[c.name for c in STRATEGY_REGISTRY]}"
        )
    return eligible


def _compute_cv_f1_scores(
    analyzer_type: AnalyzerType,
    texts: list[str],
    labels: np.ndarray,
    groups: list[str],
    n_splits: int,
) -> list[float]:
    sgkf = StratifiedGroupKFold(n_splits=n_splits)
    f1_scores: list[float] = []
    for train_idx, test_idx in sgkf.split(texts, labels, groups=groups):
        vectorizer = TfidfVectorizer(
            analyzer=analyzer_type.value, ngram_range=(1, 2), min_df=1
        )
        x_train = vectorizer.fit_transform([texts[i] for i in train_idx])
        x_test = vectorizer.transform([texts[i] for i in test_idx])
        clf = LogisticRegression(max_iter=1000, random_state=42)
        clf.fit(x_train, labels[train_idx])
        preds = clf.predict(x_test)
        f1_scores.append(f1_score(labels[test_idx], preds, zero_division=0))
    return f1_scores


def evaluate_vectorizer_subset(
    analyzer_type: AnalyzerType,
    custom_texts: list[str],
    custom_labels: np.ndarray,
    custom_groups: list[str],
) -> tuple[float, float]:
    if len(custom_texts) < 2 or len(np.unique(custom_labels)) < 2:
        return 0.0, 0.0

    min_class_samples = int(min(np.bincount(custom_labels)))
    n_splits = min(5, len(set(custom_groups)), min_class_samples)

    if n_splits < 2:
        return 0.0, 0.0

    try:
        f1_scores = _compute_cv_f1_scores(
            analyzer_type, custom_texts, custom_labels, custom_groups, n_splits
        )
        if not f1_scores:
            return 0.0, 0.0
        return float(np.mean(f1_scores)), float(np.std(f1_scores))
    except ValueError:
        return 0.0, 0.0


def generate_dataset(config: GenerationConfig) -> list[LogicTestCase]:
    """Generate SAT/UNSAT pairs cycling through all compatible strategies."""
    dataset: list[LogicTestCase] = []
    for target_mus_size in config.mus_sizes:
        eligible = _eligible_strategies(target_mus_size)
        for i in range(config.pairs_per_group):
            strategy_cls = eligible[i % len(eligible)]
            generator = BenchmarkGenerator(
                strategy=strategy_cls(),
                total_rules=config.total_rules,
                base_seed=config.base_seed,
                pack_id=strategy_cls.forced_pack_id,
            )
            sat_case, unsat_case = generator.generate_pair(
                mus_size=target_mus_size, index_in_batch=i
            )
            dataset.append(sat_case)
            dataset.append(unsat_case)
    return dataset


def verify_dataset_correctness(
    dataset: list[LogicTestCase],
) -> DatasetValidationMetrics:
    metrics = DatasetValidationMetrics()
    for case in dataset:
        result = verify_case(case)
        if case.is_satisfiable:
            if result.is_sat_correct:
                metrics.sat_valid += 1
        else:
            if result.is_sat_correct:
                metrics.unsat_valid += 1
            if result.is_mus_valid:
                metrics.mus_valid += 1
            if result.is_mus_minimal:
                metrics.mus_minimal += 1
    return metrics


def _leakage_for_subset(
    texts: list[str],
    labels: np.ndarray,
    groups: list[str],
) -> dict[str, TfidfMetrics]:
    word_m, word_s = evaluate_vectorizer_subset(
        AnalyzerType.WORD, texts, labels, groups
    )
    char_m, char_s = evaluate_vectorizer_subset(
        AnalyzerType.CHAR_WB, texts, labels, groups
    )
    return {
        MetricType.WORD_TFIDF.value: TfidfMetrics(
            mean_f1=round(word_m, 4), std_f1=round(word_s, 4)
        ),
        MetricType.CHAR_TFIDF.value: TfidfMetrics(
            mean_f1=round(char_m, 4), std_f1=round(char_s, 4)
        ),
    }


def calculate_leakage(
    dataset: list[LogicTestCase], mus_sizes: list[int]
) -> LeakageReport:
    texts = [" ".join([r.text for r in case.rules]) for case in dataset]
    labels = np.array([0 if case.is_satisfiable else 1 for case in dataset])
    groups = [str(case.template_pack_id) for case in dataset]

    global_metrics = _leakage_for_subset(texts, labels, groups)

    leakage_by_mus_size: dict[str, dict[str, TfidfMetrics]] = {}
    for target_mus_size in mus_sizes:
        indices = [
            idx for idx, case in enumerate(dataset) if case.mus_size == target_mus_size
        ]
        sub_texts = [texts[idx] for idx in indices]
        sub_labels = labels[indices]
        sub_groups = [groups[idx] for idx in indices]
        leakage_by_mus_size[f"mus_size={target_mus_size}"] = _leakage_for_subset(
            sub_texts, sub_labels, sub_groups
        )

    word_metric = global_metrics[MetricType.WORD_TFIDF.value]
    char_metric = global_metrics[MetricType.CHAR_TFIDF.value]

    return LeakageReport(
        global_word=(word_metric.mean_f1, word_metric.std_f1),
        global_char=(char_metric.mean_f1, char_metric.std_f1),
        by_mus_size=leakage_by_mus_size,
    )


def save_artifacts(
    dataset: list[LogicTestCase],
    metrics: DatasetValidationMetrics,
    leakage: LeakageReport,
    config: GenerationConfig,
    storage: StorageProtocol,
) -> None:
    dataset_file = ManifestFilename.DATASET_JSONL.value
    output_path = storage.save_dataset(dataset_file, dataset)

    source_bundle_hash = compute_source_bundle_hash()

    total_cases = len(dataset)
    half = total_cases // 2

    manifest = BenchmarkManifest(
        artifacts=ArtifactsManifest(
            dataset_filename=dataset_file,
            dataset_sha256=compute_file_sha256(output_path),
            source_bundle_sha256=source_bundle_hash,
        ),
        environment=EnvironmentManifest(
            python=platform.python_version(),
            z3=z3.get_version_string(),
            numpy=np.__version__,
            scikit_learn=sklearn.__version__,
        ),
        parameters=ParametersManifest(
            mus_sizes=config.mus_sizes,
            pairs_per_group=config.pairs_per_group,
            total_cases=total_cases,
            rules_per_case=config.total_rules,
            base_seed=config.base_seed,
        ),
        validation_results=ValidationResultsManifest(
            sat_correctness=f"{metrics.sat_valid}/{half}",
            unsat_correctness=f"{metrics.unsat_valid}/{half}",
            mus_validity=f"{metrics.mus_valid}/{half}",
            mus_minimality=f"{metrics.mus_minimal}/{half}",
        ),
        leakage_metrics_global=LeakageMetricsGlobal(
            word_tfidf=TfidfMetrics(
                mean_f1=round(leakage.global_word[0], 4),
                std_f1=round(leakage.global_word[1], 4),
            ),
            char_tfidf=TfidfMetrics(
                mean_f1=round(leakage.global_char[0], 4),
                std_f1=round(leakage.global_char[1], 4),
            ),
        ),
        leakage_metrics_by_mus_size=leakage.by_mus_size,
    )

    manifest_path = storage.save_manifest(
        ManifestFilename.MANIFEST_JSON.value, manifest
    )
    logger.info("Dataset saved to %s", output_path)
    logger.info("Manifest saved to %s", manifest_path)


def run_generation(config: GenerationConfig) -> None:
    """Library entry point for dataset generation (no CLI parsing)."""
    logger.info("Starting generation and verification pipeline...")

    dataset = generate_dataset(config)
    logger.info("Generated cases: %d", len(dataset))

    metrics = verify_dataset_correctness(dataset)
    half = len(dataset) // 2

    logger.info("=" * 50)
    logger.info("Z3 AND LOGICAL VALIDATION REPORT")
    logger.info("=" * 50)
    logger.info("SAT correctness   : %d/%d", metrics.sat_valid, half)
    logger.info("UNSAT correctness : %d/%d", metrics.unsat_valid, half)
    logger.info("MUS validity      : %d/%d", metrics.mus_valid, half)
    logger.info("MUS minimality    : %d/%d", metrics.mus_minimal, half)
    logger.info("=" * 50)

    leakage = calculate_leakage(dataset, config.mus_sizes)

    logger.info("=" * 50)
    logger.info("LEAKAGE DIAGNOSTICS REPORT (BY MUS SIZE)")
    logger.info("=" * 50)
    for mus_size_key, leak_metrics in leakage.by_mus_size.items():
        logger.info(
            "%s -> Word F1: %.4f | Char F1: %.4f",
            mus_size_key,
            leak_metrics[MetricType.WORD_TFIDF.value].mean_f1,
            leak_metrics[MetricType.CHAR_TFIDF.value].mean_f1,
        )
    logger.info("=" * 50)

    storage = FileStorageManager(config.output_dir)
    save_artifacts(
        dataset=dataset,
        metrics=metrics,
        leakage=leakage,
        config=config,
        storage=storage,
    )
