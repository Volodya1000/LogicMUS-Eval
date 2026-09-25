import argparse
import platform
from pathlib import Path
from typing import Any

import numpy as np
import sklearn  # type: ignore
import z3  # type: ignore
from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
from sklearn.linear_model import LogisticRegression  # type: ignore
from sklearn.metrics import f1_score  # type: ignore
from sklearn.model_selection import StratifiedGroupKFold  # type: ignore

from src.enums import MetricType
from src.generator import BenchmarkGenerator
from src.hashing import compute_file_sha256, compute_source_hash
from src.models.manifests import (
    ArtifactsManifest,
    BenchmarkManifest,
    EnvironmentManifest,
    LeakageMetricsGlobal,
    ParametersManifest,
    TfidfMetrics,
)
from src.models.test_case import LogicTestCase
from src.patterns.chain import ChainPatternStrategy
from src.storage import FileStorageManager, StorageProtocol
from src.verifier import verify_case


def evaluate_vectorizer_subset(
        analyzer_type: str, custom_texts: list[str],
        custom_labels: np.ndarray, custom_groups: list[str]
) -> tuple[float, float]:
    sgkf = StratifiedGroupKFold(n_splits=5)
    f1_scores = []
    for train_idx, test_idx in sgkf.split(custom_texts, custom_labels, groups=custom_groups):
        vectorizer = TfidfVectorizer(analyzer=analyzer_type, ngram_range=(1, 2), min_df=1)
        x_train = vectorizer.fit_transform([custom_texts[i] for i in train_idx])
        x_test = vectorizer.transform([custom_texts[i] for i in test_idx])
        y_train, y_test = custom_labels[train_idx], custom_labels[test_idx]
        clf = LogisticRegression(max_iter=1000, random_state=42)
        clf.fit(x_train, y_train)
        preds = clf.predict(x_test)
        f1_scores.append(f1_score(y_test, preds, zero_division=0))
    return (
        float(np.mean(f1_scores)) if f1_scores else 0.0,
        float(np.std(f1_scores)) if f1_scores else 0.0,
    )


def generate_dataset(
        generator: BenchmarkGenerator, mus_sizes: list[int], pairs: int
) -> list[LogicTestCase]:
    dataset: list[LogicTestCase] = []
    for target_mus_size in mus_sizes:
        for i in range(pairs):
            sat_case, unsat_case = generator.generate_pair(
                mus_size=target_mus_size, index_in_batch=i
            )
            dataset.append(sat_case)
            dataset.append(unsat_case)
    return dataset


def verify_dataset_correctness(dataset: list[LogicTestCase]) -> dict[str, int]:
    metrics: dict[str, int] = {
        "sat_valid": 0, "unsat_valid": 0, "mus_valid": 0, "mus_minimal": 0,
    }
    for case in dataset:
        result = verify_case(case)
        if case.is_satisfiable:
            if result.is_sat_correct:
                metrics["sat_valid"] += 1
        else:
            if result.is_sat_correct:
                metrics["unsat_valid"] += 1
            if result.is_mus_valid:
                metrics["mus_valid"] += 1
            if result.is_mus_minimal:
                metrics["mus_minimal"] += 1
    return metrics


# pylint: disable=too-many-locals
def calculate_leakage(
        dataset: list[LogicTestCase], mus_sizes: list[int]
) -> dict[str, Any]:
    texts = [" ".join([r.text for r in case.rules]) for case in dataset]
    labels = np.array([0 if case.is_satisfiable else 1 for case in dataset])
    groups = [str(case.template_pack_id) for case in dataset]

    word_m, word_s = evaluate_vectorizer_subset("word", texts, labels, groups)
    char_m, char_s = evaluate_vectorizer_subset("char_wb", texts, labels, groups)

    leakage_by_mus_size: dict[str, dict[str, TfidfMetrics]] = {}
    for target_mus_size in mus_sizes:
        indices = [idx for idx, case in enumerate(dataset) if case.mus_size == target_mus_size]
        sub_texts = [texts[idx] for idx in indices]
        sub_labels = labels[indices]
        sub_groups = [groups[idx] for idx in indices]

        w_m, w_s = evaluate_vectorizer_subset("word", sub_texts, sub_labels, sub_groups)
        c_m, c_s = evaluate_vectorizer_subset("char_wb", sub_texts, sub_labels, sub_groups)

        leakage_by_mus_size[f"mus_size={target_mus_size}"] = {
            MetricType.WORD_TFIDF.value: TfidfMetrics(mean_f1=round(w_m, 4), std_f1=round(w_s, 4)),
            MetricType.CHAR_TFIDF.value: TfidfMetrics(mean_f1=round(c_m, 4), std_f1=round(c_s, 4)),
        }

    return {
        "global_word": (word_m, word_s),
        "global_char": (char_m, char_s),
        "by_mus_size": leakage_by_mus_size
    }


def save_artifacts(
        dataset: list[LogicTestCase],
        metrics: dict[str, int],
        leakage: dict[str, Any],
        args: argparse.Namespace,
        storage: StorageProtocol
) -> None:
    dataset_file = "dataset_v1_frozen.jsonl"
    output_path = storage.save_dataset(dataset_file, dataset)

    source_bundle_hash = compute_source_hash([
        Path("src/models/rules.py"), Path("src/models/test_case.py"),
        Path("src/models/manifests.py"), Path("src/templates.py"),
        Path("src/generator.py"), Path("src/verifier.py"),
        Path("src/run_pipeline.py"), Path("src/storage.py"),
        Path("src/hashing.py"),
    ])

    total_cases = len(dataset)
    half = total_cases // 2
    global_word = leakage["global_word"]
    global_char = leakage["global_char"]

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
            mus_sizes=args.mus_sizes, pairs_per_group=args.pairs_per_group,
            total_cases=total_cases, rules_per_case=args.total_rules,
            base_seed=args.base_seed,
        ),
        validation_results={
            "sat_correctness": f"{metrics['sat_valid']}/{half}",
            "unsat_correctness": f"{metrics['unsat_valid']}/{half}",
            "mus_validity": f"{metrics['mus_valid']}/{half}",
            "mus_minimality": f"{metrics['mus_minimal']}/{half}",
        },
        leakage_metrics_global=LeakageMetricsGlobal(
            word_tfidf=TfidfMetrics(
                mean_f1=round(global_word[0], 4),
                std_f1=round(global_word[1], 4)
            ),
            char_tfidf=TfidfMetrics(
                mean_f1=round(global_char[0], 4),
                std_f1=round(global_char[1], 4)
            ),
        ),
        leakage_metrics_by_mus_size=leakage["by_mus_size"],
    )

    manifest_path = storage.save_manifest("dataset_v1_frozen.manifest.json", manifest)
    print(f"Dataset saved to {output_path}")
    print(f"Manifest saved to {manifest_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mus-sizes", type=int, nargs="+", default=[2, 3, 4, 5])
    parser.add_argument("--pairs-per-group", type=int, default=25)
    parser.add_argument("--total-rules", type=int, default=20)
    parser.add_argument("--base-seed", type=int, default=42)
    parser.add_argument("--output-dir", type=str, default="data/generated_cases")
    args = parser.parse_args()

    print("Starting generation and verification pipeline...")
    generator = BenchmarkGenerator(
        strategy=ChainPatternStrategy(),
        total_rules=args.total_rules,
        base_seed=args.base_seed
    )

    dataset = generate_dataset(generator, args.mus_sizes, args.pairs_per_group)
    print(f"Generated cases: {len(dataset)}")

    metrics = verify_dataset_correctness(dataset)
    half = len(dataset) // 2

    print("\n" + "=" * 50)
    print("Z3 AND LOGICAL VALIDATION REPORT")
    print("=" * 50)
    print(f"SAT correctness   : {metrics['sat_valid']}/{half}")
    print(f"UNSAT correctness : {metrics['unsat_valid']}/{half}")
    print(f"MUS validity      : {metrics['mus_valid']}/{half}")
    print(f"MUS minimality    : {metrics['mus_minimal']}/{half}")
    print("=" * 50)

    leakage = calculate_leakage(dataset, args.mus_sizes)

    print("\n" + "=" * 50)
    print("LEAKAGE DIAGNOSTICS REPORT (BY MUS SIZE)")
    print("=" * 50)
    for mus_size_key, leak_metrics in leakage["by_mus_size"].items():
        print(
            f"{mus_size_key} -> Word F1: {leak_metrics[MetricType.WORD_TFIDF.value].mean_f1} | "
            f"Char F1: {leak_metrics[MetricType.CHAR_TFIDF.value].mean_f1}"
        )
    print("=" * 50)

    storage = FileStorageManager(args.output_dir)
    save_artifacts(dataset, metrics, leakage, args, storage)


if __name__ == "__main__":
    main()
