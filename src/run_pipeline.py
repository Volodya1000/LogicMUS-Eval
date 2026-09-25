import hashlib
import json
import platform
from pathlib import Path

import numpy as np
import sklearn
import z3
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import StratifiedGroupKFold

from src.generator import BenchmarkGenerator
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
from src.verifier import verify_case


def compute_file_sha256(file_path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def evaluate_vectorizer_subset(
        analyzer_type: str,
        custom_texts: list[str],
        custom_labels: np.ndarray,
        custom_groups: list[str],
) -> tuple[float, float]:
    sgkf = StratifiedGroupKFold(n_splits=5)
    f1_scores = []
    for train_idx, test_idx in sgkf.split(
            custom_texts, custom_labels, groups=custom_groups
    ):
        vectorizer = TfidfVectorizer(
            analyzer=analyzer_type, ngram_range=(1, 2), min_df=1
        )
        X_train = vectorizer.fit_transform([custom_texts[i] for i in train_idx])
        X_test = vectorizer.transform([custom_texts[i] for i in test_idx])
        y_train, y_test = custom_labels[train_idx], custom_labels[test_idx]
        clf = LogisticRegression(max_iter=1000, random_state=42)
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)
        f1_scores.append(f1_score(y_test, preds, zero_division=0))
    return (
        float(np.mean(f1_scores)) if f1_scores else 0.0,
        float(np.std(f1_scores)) if f1_scores else 0.0,
    )


def main() -> None:
    print("Starting generation and verification pipeline...")
    strategy = ChainPatternStrategy()
    generator = BenchmarkGenerator(strategy=strategy, total_rules_count=20, base_seed=42)
    dataset: list[LogicTestCase] = []

    k_values = [2, 3, 4, 5]
    pairs_per_group = 25

    for k in k_values:
        for i in range(pairs_per_group):
            sat_case, unsat_case = generator.generate_pair(mus_size=k, index_in_batch=i)
            dataset.append(sat_case)
            dataset.append(unsat_case)

    total_cases = len(dataset)
    print(f"Generated cases: {total_cases}")

    sat_valid_count = 0
    unsat_valid_count = 0
    mus_valid_count = 0
    mus_minimal_count = 0

    for case in dataset:
        result = verify_case(case)
        if case.is_satisfiable:
            if result.is_sat_correct:
                sat_valid_count += 1
        else:
            if result.is_sat_correct:
                unsat_valid_count += 1
            if result.is_mus_valid:
                mus_valid_count += 1
            if result.is_mus_minimal:
                mus_minimal_count += 1

    total_sat_cases = total_cases // 2
    total_unsat_cases = total_cases // 2

    print("\n" + "=" * 50)
    print("Z3 AND LOGICAL VALIDATION REPORT")
    print("=" * 50)
    print(f"SAT correctness   : {sat_valid_count}/{total_sat_cases}")
    print(f"UNSAT correctness : {unsat_valid_count}/{total_unsat_cases}")
    print(f"MUS validity      : {mus_valid_count}/{total_unsat_cases}")
    print(f"MUS minimality    : {mus_minimal_count}/{total_unsat_cases}")
    print("=" * 50)

    output_dir = Path("data/generated_cases")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / "dataset_v1_frozen.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for case in dataset:
            f.write(json.dumps(case.to_dict(), ensure_ascii=False) + "\n")

    texts = [" ".join([r.text for r in case.rules]) for case in dataset]
    labels = np.array([0 if case.is_satisfiable else 1 for case in dataset])
    groups = [str(case.template_pack_id) for case in dataset]

    word_mean, word_std = evaluate_vectorizer_subset("word", texts, labels, groups)
    char_mean, char_std = evaluate_vectorizer_subset("char_wb", texts, labels, groups)

    leakage_by_k: dict[str, dict[str, TfidfMetrics]] = {}
    for k_val in k_values:
        indices = [idx for idx, case in enumerate(dataset) if case.k == k_val]
        sub_texts = [texts[idx] for idx in indices]
        sub_labels = labels[indices]
        sub_groups = [groups[idx] for idx in indices]

        w_m, w_s = evaluate_vectorizer_subset("word", sub_texts, sub_labels, sub_groups)
        c_m, c_s = evaluate_vectorizer_subset("char_wb", sub_texts, sub_labels, sub_groups)

        leakage_by_k[f"k={k_val}"] = {
            "word_tfidf": TfidfMetrics(mean_f1=round(w_m, 4), std_f1=round(w_s, 4)),
            "char_tfidf": TfidfMetrics(mean_f1=round(c_m, 4), std_f1=round(c_s, 4)),
        }

    print("\n" + "=" * 50)
    print("LEAKAGE DIAGNOSTICS REPORT (BY K)")
    print("=" * 50)
    for k_key, metrics in leakage_by_k.items():
        print(
            f"{k_key} -> Word F1: {metrics['word_tfidf'].mean_f1} | "
            f"Char F1: {metrics['char_tfidf'].mean_f1}"
        )
    print("=" * 50)

    source_files = [
        Path("src/models/rules.py"),
        Path("src/models/test_case.py"),
        Path("src/models/manifests.py"),
        Path("src/templates.py"),
        Path("src/generator.py"),
        Path("src/verifier.py"),
        Path("src/run_pipeline.py"),
    ]
    hasher = hashlib.sha256()
    for sf in source_files:
        if sf.exists():
            hasher.update(sf.read_bytes())
    source_bundle_hash = hasher.hexdigest()

    manifest = BenchmarkManifest(
        artifacts=ArtifactsManifest(
            dataset_filename=output_path.name,
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
            k_values=k_values,
            pairs_per_group=pairs_per_group,
            total_cases=len(dataset),
            rules_per_case=20,
            base_seed=42,
        ),
        validation_results={
            "sat_correctness": f"{sat_valid_count}/{total_sat_cases}",
            "unsat_correctness": f"{unsat_valid_count}/{total_unsat_cases}",
            "mus_validity": f"{mus_valid_count}/{total_unsat_cases}",
            "mus_minimality": f"{mus_minimal_count}/{total_unsat_cases}",
        },
        leakage_metrics_global=LeakageMetricsGlobal(
            word_tfidf=TfidfMetrics(mean_f1=round(word_mean, 4), std_f1=round(word_std, 4)),
            char_tfidf=TfidfMetrics(mean_f1=round(char_mean, 4), std_f1=round(char_std, 4)),
        ),
        leakage_metrics_by_k=leakage_by_k,
    )

    manifest_path = output_dir / "dataset_v1_frozen.manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(manifest.model_dump_json(indent=2))

    print(f"Dataset saved to {output_path}")
    print(f"Manifest saved to {manifest_path}")


if __name__ == "__main__":
    main()
