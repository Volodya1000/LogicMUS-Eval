"""Typed summaries from the shared finalized-outcome metric semantics."""

from collections import Counter, defaultdict

from logicmus_eval.analysis.models import (
    AnalysisDimensions,
    AnalysisRow,
    ConfidenceInterval,
    ScoredObservation,
    SummaryResult,
)
from logicmus_eval.analysis.plan import AnalysisPlan, Metric
from logicmus_eval.analysis.statistics import cluster_interval, unavailable, wilson
from logicmus_eval.evaluation.metrics import aggregate_outcomes as metrics_for
from logicmus_eval.evaluation.metrics import semantics
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


def error_bucket(outcome: EvaluationCaseReport) -> str:
    """Exclusive priority: refusal, primary error, invalid, wrong SAT/MUS, correct."""
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


def observations(rows: list[AnalysisRow], metric: Metric) -> list[ScoredObservation]:
    return [
        ScoredObservation(row, value)
        for row in rows
        if (value := semantics.observation(row.outcome, metric)) is not None
    ]


def _interval(
    scored: list[ScoredObservation], metric: Metric, plan: AnalysisPlan
) -> ConfidenceInterval:
    families = [item.row.provenance.family_id for item in scored]
    settings = plan.intervals
    if metric == "mus_exact_match":
        if len(families) != len(set(families)):
            return unavailable(
                "Wilson requires exactly one UNSAT observation per family",
                len(set(families)),
            )
        return wilson(
            int(sum(item.value for item in scored)),
            len(scored),
            settings.level,
            settings.min_families,
        )
    return cluster_interval(
        [(item.row.provenance.family_id, item.value) for item in scored],
        seed=settings.seed,
        repeats=settings.repeats,
        level=settings.level,
        min_families=settings.min_families,
    )


def summary_table(rows: list[AnalysisRow], plan: AnalysisPlan) -> list[SummaryResult]:
    cells: dict[AnalysisDimensions, list[AnalysisRow]] = defaultdict(list)
    for row in rows:
        cells[row.dimensions].append(row)
    result = []
    for dimensions, cell in sorted(cells.items()):
        buckets = Counter(error_bucket(row.outcome) for row in cell)
        intervals = {
            metric: _interval(observations(cell, metric), metric, plan)
            for metric in dict.fromkeys([plan.primary_metric, *plan.additional_metrics])
        }
        result.append(
            SummaryResult(
                dimensions,
                metrics_for([row.outcome for row in cell], len(cell)),
                len({row.provenance.family_id for row in cell}),
                len(
                    {
                        item.row.provenance.family_id
                        for item in observations(cell, "mus_f1")
                    }
                ),
                sorted({row.run_id for row in cell}),
                dict(sorted(buckets.items())),
                {name: count / len(cell) for name, count in sorted(buckets.items())},
                intervals,
            )
        )
    return result
