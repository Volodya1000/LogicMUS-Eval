"""Independent numerical and clustering regressions (no LLM)."""

import pytest

from logicmus_eval.analysis.statistics import cluster_interval, wilson
from logicmus_eval.analysis.tables import metrics_for
from logicmus_eval.models.evaluation import EvaluationCaseReport


def test_wilson_known_reference_and_insufficient():
    result = wilson(7, 10)
    assert result["low"] == pytest.approx(0.396778, abs=1e-5)
    assert result["high"] == pytest.approx(0.892209, abs=1e-5)
    assert wilson(0, 0)["status"] == "unavailable"
    assert wilson(1, 1)["status"] == "unavailable"


def test_cluster_bootstrap_carries_families_and_sorts_input():
    # Each family has unequal size. The target is the row-weighted macro mean;
    # resampling rows would invent values not in {0, 1/4, 1} here.
    rows = [("a", 0.0), ("a", 0.0), ("a", 0.0), ("b", 1.0)]
    result = cluster_interval(rows, seed=42, repeats=1000)
    assert result == cluster_interval(list(reversed(rows)), seed=42, repeats=1000)
    assert result["low"] == 0
    assert result["high"] == 1
    assert result["families"] == 2
    assert cluster_interval([("a", 1.0)], seed=1)["status"] == "unavailable"
    flat = cluster_interval([("a", 0.0), ("b", 0.0)], seed=1)
    assert flat["degenerate"] is True
    assert flat["low"] == flat["high"] == 0


def test_macro_f1_is_mean_of_normalized_outcomes():
    outcomes = []
    for precision, recall, f1 in [(1, 0.5, 2 / 3), (0.5, 1, 2 / 3), (0, 0, 0)]:
        outcomes.append(
            EvaluationCaseReport(
                case_id=str(len(outcomes)),
                mus_size=2,
                expected_sat=False,
                predicted_sat=False,
                is_sat_correct=True,
                expected_mus=["a", "b"],
                predicted_mus=[],
                is_mus_correct=False,
                metadata={},
                reasoning="",
                mus_precision=precision,
                mus_recall=recall,
                mus_f1=f1,
            )
        )
    result = metrics_for(outcomes, 3)
    assert result["mus_precision"] == result["mus_recall"] == 0.5
    assert result["mus_f1"] == pytest.approx(4 / 9)
