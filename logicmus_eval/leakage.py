"""Pair-held-out lexical diagnostics; passing a probe is not proof of no leakage."""

import numpy as np
from sklearn.feature_extraction.text import (  # type: ignore[import-untyped]
    TfidfVectorizer,
)
from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
from sklearn.metrics import (  # type: ignore[import-untyped]
    balanced_accuracy_score,
    f1_score,
)
from sklearn.model_selection import StratifiedGroupKFold  # type: ignore[import-untyped]

from logicmus_eval.enums import AnalyzerType, MetricType
from logicmus_eval.models.manifests import TfidfMetrics
from logicmus_eval.models.pipeline import LeakageReport
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.prompt_formatting import format_rules_block, format_variable_block


def case_group(case: LogicTestCase) -> str:
    """Hold an entire controlled family out, with unchanged legacy fallback."""
    if case.metadata.get("family_id"):
        return str(case.metadata["family_id"])
    legacy_id = case.case_id.replace("_UNSAT_", "_").replace("_SAT_", "_")
    legacy_pair = f"{case.mus_size}:{case.metadata.get('case_seed', legacy_id)}"
    return str(case.metadata.get("pair_id") or legacy_pair)


def grouped_splits(
    labels: list[int], groups: list[str]
) -> list[tuple[np.ndarray, np.ndarray]]:
    if len(labels) != len(groups) or set(labels) != {0, 1}:
        raise ValueError("Need equal-length labels/groups and both binary classes")
    n_splits = min(5, len(set(groups)), labels.count(0), labels.count(1))
    if n_splits < 2:
        raise ValueError("Need at least two independent SAT/UNSAT pairs")
    splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=42)
    splits = list(splitter.split(np.zeros(len(labels)), labels, groups))
    for train, test in splits:
        if len({labels[i] for i in train}) != 2 or len({labels[i] for i in test}) != 2:
            raise ValueError("Every train/test fold must contain both classes")
    return splits


def evaluate_vectorizer_subset(
    analyzer_type: AnalyzerType, texts: list[str], labels: list[int], groups: list[str]
) -> TfidfMetrics:
    try:
        if len(texts) != len(labels):
            raise ValueError("texts/labels length mismatch")
        splits = grouped_splits(labels, groups)
        f1_scores, balanced_scores = [], []
        for train, test in splits:
            vectorizer = TfidfVectorizer(
                analyzer=analyzer_type.value,
                ngram_range=(1, 2) if analyzer_type == AnalyzerType.WORD else (3, 5),
            )
            x_train = vectorizer.fit_transform([texts[i] for i in train])
            classifier = LogisticRegression(max_iter=1000, random_state=42)
            classifier.fit(x_train, [labels[i] for i in train])
            predicted = classifier.predict(
                vectorizer.transform([texts[i] for i in test])
            )
            expected = [labels[i] for i in test]
            f1_scores.append(float(f1_score(expected, predicted, zero_division=0)))
            balanced_scores.append(float(balanced_accuracy_score(expected, predicted)))
        return TfidfMetrics(
            mean_f1=float(np.mean(f1_scores)),
            std_f1=float(np.std(f1_scores)),
            mean_balanced_accuracy=float(np.mean(balanced_scores)),
            std_balanced_accuracy=float(np.std(balanced_scores)),
            fold_balanced_accuracies=balanced_scores,
            n_splits=len(splits),
            status="ok",
        )
    except ValueError as error:
        return TfidfMetrics(status="unavailable", reason=str(error))


def calculate_leakage(
    dataset: list[LogicTestCase], mus_sizes: list[int]
) -> LeakageReport:
    # Use the actual model-visible rule structure and variable declarations,
    # excluding service metadata.
    direct_texts = [format_rules_block(case) for case in dataset]
    labels = [int(not case.is_satisfiable) for case in dataset]
    groups = [case_group(case) for case in dataset]

    def subset(texts: list[str], indices: list[int]) -> dict[str, TfidfMetrics]:
        return {
            metric.value: evaluate_vectorizer_subset(
                analyzer,
                [texts[i] for i in indices],
                [labels[i] for i in indices],
                [groups[i] for i in indices],
            )
            for metric, analyzer in (
                (MetricType.WORD_TFIDF, AnalyzerType.WORD),
                (MetricType.CHAR_TFIDF, AnalyzerType.CHAR_WB),
            )
        }

    views = {}
    for name, texts in (
        ("direct", direct_texts),
        (
            "z3",
            [
                text + format_variable_block(case)
                for text, case in zip(direct_texts, dataset)
            ],
        ),
    ):
        views[name] = {
            "global": subset(texts, list(range(len(dataset)))),
            **{
                f"mus_size={k}": subset(
                    texts, [i for i, c in enumerate(dataset) if c.mus_size == k]
                )
                for k in mus_sizes
            },
        }
    overall = views["direct"]["global"]
    return LeakageReport(
        global_word=overall[MetricType.WORD_TFIDF.value],
        global_char=overall[MetricType.CHAR_TFIDF.value],
        by_mus_size={
            f"mus_size={k}": views["direct"][f"mus_size={k}"] for k in mus_sizes
        },
        by_input=views,
    )
