import pytest

from logicmus_eval.enums import AnalyzerType
from logicmus_eval.run_pipeline import (
    GenerationConfig,
    calculate_leakage,
    generate_dataset,
)


def test_leakage_report_has_chance_calibrated_scores():
    dataset = generate_dataset(GenerationConfig([3], 12, 10, 42, "unused"))
    for case in dataset:
        for rule in case.rules:
            rule.text = "одинаковый текст"
    for sat, unsat in zip(dataset[::2], dataset[1::2]):
        unsat.rules = [r.model_copy(deep=True) for r in sat.rules]
    report = calculate_leakage(dataset, [3])
    assert report.global_word.mean_balanced_accuracy == 0.5
    assert report.global_char.mean_balanced_accuracy == 0.5
    assert report.acceptance(0.55).passed is True


def test_unavailable_cv_is_not_a_perfect_no_leak_result():
    dataset = generate_dataset(GenerationConfig([2], 1, 5, 42, "unused"))
    report = calculate_leakage(dataset, [2])
    assert report.global_word.status == "unavailable"
    assert report.global_word.mean_balanced_accuracy is None
    assert report.acceptance(0.55).passed is False


def test_obvious_lexical_leak_is_detected():
    dataset = generate_dataset(GenerationConfig([3], 30, 10, 42, "unused"))
    for case in dataset:
        for rule in case.rules:
            rule.text = "выполнимо" if case.is_satisfiable else "противоречие"
    report = calculate_leakage(dataset, [3])
    assert report.global_word.mean_balanced_accuracy == 1.0
    assert report.acceptance(0.55).passed is False


def test_invalid_probe_input_remains_visible():
    from logicmus_eval.leakage import evaluate_vectorizer_subset

    result = evaluate_vectorizer_subset(
        AnalyzerType.WORD, ["", "", "", ""], [0, 1, 0, 1], ["a", "a", "b", "b"]
    )
    assert result.status == "unavailable"
    assert result.mean_f1 is None
    assert result.reason


def test_threshold_is_inclusive_and_validated():
    from logicmus_eval.models.manifests import TfidfMetrics
    from logicmus_eval.models.pipeline import LeakageReport

    metric = TfidfMetrics(
        mean_f1=0.6,
        std_f1=0.0,
        mean_balanced_accuracy=0.55,
        std_balanced_accuracy=0.0,
        status="ok",
        n_splits=2,
        fold_balanced_accuracies=[0.5, 0.6],
    )
    report = LeakageReport(
        global_word=metric,
        global_char=metric,
        by_mus_size={"mus_size=2": {"word_tfidf": metric, "char_tfidf": metric}},
    )
    assert report.acceptance(0.55).passed
    assert not report.acceptance(0.54).passed
    with pytest.raises(ValueError):
        report.acceptance(0.49)


def test_pairs_are_kept_together_in_cv():
    from logicmus_eval.leakage import grouped_splits

    groups = [str(i // 2) for i in range(20)]
    splits = grouped_splits([0, 1] * 10, groups)
    assert len(splits) == 5
    for train, test in splits:
        assert not ({groups[i] for i in train} & {groups[i] for i in test})


@pytest.mark.parametrize("score", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_measurements_cannot_pass(score):
    from logicmus_eval.models.manifests import TfidfMetrics
    from logicmus_eval.models.pipeline import LeakageReport

    metric = TfidfMetrics(
        mean_balanced_accuracy=score,
        status="ok",
        n_splits=2,
        fold_balanced_accuracies=[score, score],
    )
    report = LeakageReport(
        global_word=metric,
        global_char=metric,
        by_mus_size={"mus_size=2": {"word_tfidf": metric, "char_tfidf": metric}},
    )
    assert not report.acceptance().passed


def test_status_ok_requires_measured_folds():
    from logicmus_eval.models.manifests import TfidfMetrics
    from logicmus_eval.models.pipeline import LeakageReport

    metric = TfidfMetrics(mean_balanced_accuracy=0.5, status="ok")
    report = LeakageReport(
        global_word=metric,
        global_char=metric,
        by_mus_size={"mus_size=2": {"word_tfidf": metric, "char_tfidf": metric}},
    )
    assert not report.acceptance().passed


def test_both_model_visible_input_views_are_probed():
    dataset = generate_dataset(GenerationConfig([3], 20, 10, 42, "unused"))
    for sat, unsat in zip(dataset[::2], dataset[1::2]):
        unsat.rules = [r.model_copy(deep=True) for r in sat.rules]
    for case in dataset:
        case.predicate_mapping = {
            var: ("satmarker" if case.is_satisfiable else "unsatmarker")
            for var in case.predicate_mapping
        }
    report = calculate_leakage(dataset, [3])
    assert report.global_word.mean_balanced_accuracy == 0.5
    assert (
        report.by_input["direct"]["global"]["word_tfidf"].mean_balanced_accuracy == 0.5
    )
    assert report.by_input["z3"]["global"]["word_tfidf"].mean_balanced_accuracy == 1.0
    assert not report.acceptance().passed
