"""Tables reuse PR #3 metric classes and saved eligibility; no MUS list parsing."""

from collections import Counter, defaultdict
from typing import Any

from pydantic import JsonValue

from logicmus_eval.analysis.plan import AnalysisPlan
from logicmus_eval.analysis.statistics import cluster_interval, unavailable, wilson
from logicmus_eval.evaluation.metrics import accounting_counts, build_metrics
from logicmus_eval.models.evaluation import EvaluationCaseReport

DIMENSIONS = [
    "group",
    "purpose",
    "series_id",
    "series_kind",
    "pattern_id",
    "K",
    "N",
    "model_id",
    "strategy",
]


def metrics_for(
    outcomes: list[EvaluationCaseReport], planned: int
) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for metric in build_metrics():
        for outcome in outcomes:
            metric.update_report(outcome)
        result.update(metric.compute())
    result.update(accounting_counts(outcomes, planned))
    return result


def error_bucket(outcome: EvaluationCaseReport) -> str:
    """Mutually exclusive priority: refusal, primary error, invalid, wrong SAT,
    wrong MUS, correct. Unknown validity never implies correctness.
    """
    if outcome.refusal is True:
        return "refusal"
    if outcome.error_type is not None:
        return "error:" + outcome.error_type.value
    if outcome.valid_response is not True:
        return "invalid_or_unknown"
    if not outcome.is_sat_correct:
        return "wrong_sat"
    if not outcome.expected_sat and not outcome.is_mus_correct:
        return "wrong_mus"
    return "correct"


def metric_value(row: dict[str, Any], metric: str) -> float:
    # PR #3 finalized outcomes have numeric MUS scores; null contributes zero to
    # UNSAT macro-F1 exactly as MusValidMetric, without re-evaluating eligibility.
    if metric == "mus_f1":
        return float(row["outcome"].mus_f1 or 0.0)
    if metric == "mus_exact_match":
        return float(row["outcome"].is_mus_correct)
    if metric == "sat_accuracy":
        return float(row["outcome"].is_sat_correct)
    if metric == "coverage":
        return float(row["outcome"].valid_response is True)
    raise ValueError(f"Unsupported metric {metric}")


def eligible(rows: list[dict[str, Any]], metric: str) -> list[dict[str, Any]]:
    return (
        [row for row in rows if not row["outcome"].expected_sat]
        if metric.startswith("mus_")
        else rows
    )


def summary_table(
    rows: list[dict[str, Any]], plan: AnalysisPlan
) -> list[dict[str, Any]]:
    cells: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cells[tuple(row[key] for key in DIMENSIONS)].append(row)
    result = []
    settings = plan.intervals.model_dump(exclude={"method"})
    for key, cell in sorted(cells.items()):
        metrics = metrics_for([row["outcome"] for row in cell], len(cell))
        record = dict(zip(DIMENSIONS, key)) | metrics
        record["families"] = len({row["family_id"] for row in cell})
        record["unsat_families"] = len(
            {row["family_id"] for row in eligible(cell, "mus_f1")}
        )
        record["run_ids"] = sorted({row["run_id"] for row in cell})
        buckets = Counter(row["error_bucket"] for row in cell)
        record["error_bucket_counts"] = dict(sorted(buckets.items()))
        record["error_bucket_fractions"] = {
            name: count / len(cell) for name, count in sorted(buckets.items())
        }
        for metric in dict.fromkeys([plan.primary_metric, *plan.additional_metrics]):
            selected = eligible(cell, metric)
            families = [row["family_id"] for row in selected]
            if metric == "mus_exact_match":
                interval = (
                    wilson(
                        sum(row["outcome"].is_mus_correct for row in selected),
                        len(selected),
                        plan.intervals.level,
                        plan.intervals.min_families,
                    )
                    if len(families) == len(set(families))
                    else unavailable(
                        "Wilson requires exactly one UNSAT observation per family",
                        len(set(families)),
                    )
                )
            else:
                interval = cluster_interval(
                    [(row["family_id"], metric_value(row, metric)) for row in selected],
                    **settings,
                )
            record.update(
                {f"{metric}_ci_{name}": value for name, value in interval.items()}
            )
        result.append(record)
    return result
