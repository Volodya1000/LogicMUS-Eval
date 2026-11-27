"""Strict planned pairs, with shared family bootstrap draws on both sides."""

from typing import Any

from logicmus_eval.analysis.plan import AnalysisPlan, Contrast, Selection
from logicmus_eval.analysis.sources import check_compatibility
from logicmus_eval.analysis.statistics import cluster_interval
from logicmus_eval.analysis.tables import DIMENSIONS, eligible, metric_value


def select(rows: list[dict[str, Any]], selection: Selection) -> list[dict[str, Any]]:
    fields = selection.model_dump(exclude_none=True)
    return [
        row for row in rows if all(row[key] == value for key, value in fields.items())
    ]


def _pairs(rows: list[dict[str, Any]], contrast: Contrast) -> dict[str, dict[str, Any]]:
    result = {}
    for row in eligible(rows, contrast.metric):
        key = (
            row["case_uid"]
            if contrast.kind == "strategy"
            else str((row["family_id"], row["outcome"].expected_sat))
        )
        if key in result:
            raise ValueError(
                "Ambiguous contrast: select one series/pattern/K/N/model/strategy per side"
            )
        result[key] = row
    return result


def contrast_table(  # pylint: disable=too-many-locals
    rows: list[dict[str, Any]], plan: AnalysisPlan, diagnostics: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    result = []
    for contrast in plan.contrasts:
        left_rows, right_rows = (
            select(rows, contrast.left),
            select(rows, contrast.right),
        )
        left, right = _pairs(left_rows, contrast), _pairs(right_rows, contrast)
        diagnostic = {
            "name": contrast.name,
            "missing_left": sorted(right.keys() - left.keys()),
            "missing_right": sorted(left.keys() - right.keys()),
        }
        diagnostics.append(diagnostic)
        if not left or not right or left.keys() != right.keys():
            raise ValueError(
                f"Contrast {contrast.name}: missing paired observations; see diagnostics.json"
            )
        for side in (left_rows, right_rows):
            if len({tuple(row[field] for field in DIMENSIONS) for row in side}) != 1:
                raise ValueError(
                    "Contrast must select exactly one cell per side; "
                    "no implicit budget/model/topology averaging"
                )
        check_compatibility(left_rows + right_rows)
        differences = []
        for key in sorted(left):
            a, b = left[key], right[key]
            fixed = [
                field for field in DIMENSIONS if field not in {"group", "N", "strategy"}
            ]
            fixed.append("family_id")
            if contrast.kind == "strategy":
                fixed += ["N", "pair_id"]
                if {a["strategy"], b["strategy"]} != {"direct", "z3"}:
                    raise ValueError("Strategy contrast requires direct versus z3")
            elif (
                a["series_kind"] != "noise_sweep"
                or a["strategy"] != b["strategy"]
                or a["N"] == b["N"]
            ):
                raise ValueError(
                    "Noise contrast requires different N in the same noise_sweep and strategy"
                )
            if any(a[field] != b[field] for field in fixed):
                raise ValueError(
                    "Paired contrast has incompatible identities; K sweeps are not paired"
                )
            if a["outcome"].expected_sat != b["outcome"].expected_sat or (
                contrast.kind == "strategy"
                and a["outcome"].expected_mus != b["outcome"].expected_mus
            ):
                raise ValueError("Paired reference outcomes differ")
            differences.append(
                (
                    a["family_id"],
                    metric_value(b, contrast.metric) - metric_value(a, contrast.metric),
                )
            )
        interval = cluster_interval(
            differences, **plan.intervals.model_dump(exclude={"method"})
        )
        result.append(
            {
                "name": contrast.name,
                "kind": contrast.kind,
                "metric": contrast.metric,
                "direction": "right-minus-left",
                "left": contrast.left.model_dump(exclude_none=True),
                "right": contrast.right.model_dump(exclude_none=True),
                "pairs": len(differences),
                "estimate": sum(value for _, value in differences) / len(differences),
                **interval,
            }
        )
    return result
