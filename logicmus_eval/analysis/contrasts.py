"""Strict planned pairs; both sides share whole-family bootstrap multiplicities."""

from logicmus_eval.analysis.models import (
    AnalysisRow,
    ContrastDiagnostic,
    ContrastResult,
    ScoredObservation,
)
from logicmus_eval.analysis.plan import AnalysisPlan, Contrast
from logicmus_eval.analysis.selection import select
from logicmus_eval.analysis.sources import check_compatibility
from logicmus_eval.analysis.statistics import cluster_interval
from logicmus_eval.analysis.tables import observations


def _pairs(rows: list[AnalysisRow], contrast: Contrast) -> dict[str, ScoredObservation]:
    result = {}
    for item in observations(rows, contrast.metric):
        row = item.row
        key = (
            row.job.case_uid
            if contrast.kind == "strategy"
            else str((row.provenance.family_id, row.outcome.expected_sat))
        )
        if key in result:
            raise ValueError(
                "Ambiguous contrast: select one series/pattern/K/N/model/strategy per side"
            )
        result[key] = item
    return result


def _validate_pair(a: AnalysisRow, b: AnalysisRow, contrast: Contrast) -> None:
    left, right = a.dimensions, b.dimensions
    if (
        left.family_key() != right.family_key()
        or a.provenance.family_id != b.provenance.family_id
    ):
        raise ValueError(
            "Paired contrast has incompatible identities; K sweeps are not paired"
        )
    if contrast.kind == "strategy":
        if {left.strategy, right.strategy} != {"direct", "z3"}:
            raise ValueError("Strategy contrast requires direct versus z3")
        if left.n != right.n or a.provenance.pair_id != b.provenance.pair_id:
            raise ValueError("Paired contrast has incompatible identities")
    elif (
        left.series_kind != "noise_sweep"
        or left.strategy != right.strategy
        or left.n == right.n
    ):
        raise ValueError(
            "Noise contrast requires different N in the same noise_sweep and strategy"
        )
    if a.outcome.expected_sat != b.outcome.expected_sat or (
        contrast.kind == "strategy" and a.outcome.expected_mus != b.outcome.expected_mus
    ):
        raise ValueError("Paired reference outcomes differ")


def _contrast(
    rows: list[AnalysisRow],
    contrast: Contrast,
    diagnostics: list[ContrastDiagnostic],
    plan: AnalysisPlan,
) -> ContrastResult:
    left_rows, right_rows = select(rows, contrast.left), select(rows, contrast.right)
    left, right = _pairs(left_rows, contrast), _pairs(right_rows, contrast)
    diagnostics.append(
        ContrastDiagnostic(
            name=contrast.name,
            missing_left=sorted(right.keys() - left.keys()),
            missing_right=sorted(left.keys() - right.keys()),
        )
    )
    if not left or not right or left.keys() != right.keys():
        raise ValueError(
            f"Contrast {contrast.name}: missing paired observations; see diagnostics.json"
        )
    for side in (left_rows, right_rows):
        if len({row.dimensions for row in side}) != 1:
            raise ValueError(
                "Contrast must select exactly one cell per side; "
                "no implicit budget/model/topology averaging"
            )
    check_compatibility(left_rows + right_rows)
    differences = []
    for key in sorted(left):
        a, b = left[key], right[key]
        _validate_pair(a.row, b.row, contrast)
        differences.append((a.row.provenance.family_id, b.value - a.value))
    settings = plan.intervals
    interval = cluster_interval(
        differences,
        seed=settings.seed,
        repeats=settings.repeats,
        level=settings.level,
        min_families=settings.min_families,
    )
    return ContrastResult(
        contrast.name,
        contrast.kind,
        contrast.metric,
        contrast.left,
        contrast.right,
        len(differences),
        sum(value for _, value in differences) / len(differences),
        interval,
    )


def contrast_table(
    rows: list[AnalysisRow], plan: AnalysisPlan, diagnostics: list[ContrastDiagnostic]
) -> list[ContrastResult]:
    return [_contrast(rows, item, diagnostics, plan) for item in plan.contrasts]
