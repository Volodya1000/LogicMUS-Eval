import logging
import platform
from dataclasses import dataclass

import numpy as np
import sklearn  # type: ignore[import-untyped]
import z3  # type: ignore[import-untyped]

from logicmus_eval.enums import ManifestFilename, MetricType
from logicmus_eval.generator import BenchmarkGenerator
from logicmus_eval.hashing import compute_file_sha256, compute_source_bundle_hash
from logicmus_eval.leakage import calculate_leakage
from logicmus_eval.models.manifests import (
    ArtifactsManifest,
    BenchmarkManifest,
    EnvironmentManifest,
    LeakageMetricsGlobal,
    ParametersManifest,
    ValidationResultsManifest,
)
from logicmus_eval.models.pipeline import DatasetValidationMetrics, LeakageReport
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.patterns.base import BasePatternStrategy
from logicmus_eval.patterns.chain import ChainPatternStrategy
from logicmus_eval.patterns.coverage import CoveragePatternStrategy
from logicmus_eval.patterns.direct import DirectPatternStrategy
from logicmus_eval.patterns.fork import ForkPatternStrategy
from logicmus_eval.patterns.idem import IdemPatternStrategy
from logicmus_eval.patterns.math import MathPatternStrategy
from logicmus_eval.patterns.merge import MergePatternStrategy
from logicmus_eval.storage import FileStorageManager, StorageProtocol
from logicmus_eval.templates import PREDICATE_POOL
from logicmus_eval.verifier import build_z3_solver, verify_case

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GenerationConfig:
    mus_sizes: list[int]
    pairs_per_group: int
    total_rules: int
    base_seed: int
    output_dir: str
    leakage_threshold: float = 0.55


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


def _eligible_strategies(
    mus_size: int, total_rules: int | None = None
) -> list[type[BasePatternStrategy]]:
    eligible = [
        cls
        for cls in STRATEGY_REGISTRY
        if cls.supports(mus_size)
        and (total_rules is None or cls.core_rule_count(mus_size) <= total_rules)
        and (
            total_rules is None
            or cls.core_variable_count(mus_size)
            + total_rules
            - cls.core_rule_count(mus_size)
            <= len(PREDICATE_POOL)
        )
    ]
    if not eligible:
        raise ValueError(
            f"No strategy supports mus_size={mus_size}. "
            f"Registry: {[c.name for c in STRATEGY_REGISTRY]}"
        )
    return eligible


def generate_dataset(config: GenerationConfig) -> list[LogicTestCase]:
    """Generate SAT/UNSAT pairs cycling through all compatible strategies."""
    if not 0.5 <= config.leakage_threshold <= 1.0:
        raise ValueError("leakage_threshold must be between 0.5 and 1.0")
    if not config.mus_sizes or len(set(config.mus_sizes)) != len(config.mus_sizes):
        raise ValueError("mus_sizes must be non-empty and contain no duplicates")
    if config.pairs_per_group < 1 or config.total_rules < 2:
        raise ValueError("pairs_per_group must be >= 1 and total_rules >= 2")
    # Validate the entire grid before constructing any case.
    for size in config.mus_sizes:
        _eligible_strategies(size, config.total_rules)
    dataset: list[LogicTestCase] = []
    for target_mus_size in config.mus_sizes:
        eligible = _eligible_strategies(target_mus_size, config.total_rules)
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
            generator_version=2,
        ),
        validation_results=ValidationResultsManifest(
            sat_correctness=f"{metrics.sat_valid}/{half}",
            unsat_correctness=f"{metrics.unsat_valid}/{half}",
            mus_validity=f"{metrics.mus_valid}/{half}",
            mus_minimality=f"{metrics.mus_minimal}/{half}",
        ),
        leakage_metrics_global=LeakageMetricsGlobal(
            word_tfidf=leakage.global_word,
            char_tfidf=leakage.global_char,
        ),
        leakage_metrics_by_mus_size=leakage.by_mus_size,
        leakage_acceptance=leakage.acceptance(
            config.leakage_threshold, config.mus_sizes, ("direct", "z3")
        ),
        leakage_metrics_by_input=leakage.by_input,
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

    if any(value != half for value in metrics.model_dump().values()):
        raise ValueError("Logical validation failed; dataset is not releasable")
    # Independent uniqueness witness: every MUS must contain every member of M
    # if removing each member makes the WHOLE instance satisfiable. Since M is
    # already minimal UNSAT, this proves uniqueness with K solver checks.
    for case in dataset:
        if case.is_satisfiable:
            continue
        for rid in case.mus_expected:
            if (
                build_z3_solver([r for r in case.rules if r.id != rid]).check()
                != z3.sat
            ):
                raise ValueError(f"MUS uniqueness validation failed for {case.case_id}")

    leakage = calculate_leakage(dataset, config.mus_sizes)

    logger.info("=" * 50)
    logger.info("LEAKAGE DIAGNOSTICS REPORT (BY MUS SIZE)")
    logger.info("=" * 50)
    for mus_size_key, leak_metrics in leakage.by_mus_size.items():
        logger.info(
            "%s -> Word balanced accuracy: %s | Char balanced accuracy: %s",
            mus_size_key,
            leak_metrics[MetricType.WORD_TFIDF.value].mean_balanced_accuracy,
            leak_metrics[MetricType.CHAR_TFIDF.value].mean_balanced_accuracy,
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
    acceptance = leakage.acceptance(
        config.leakage_threshold, config.mus_sizes, ("direct", "z3")
    )
    if not acceptance.passed:
        raise ValueError("Leakage audit failed: " + "; ".join(acceptance.failures))
