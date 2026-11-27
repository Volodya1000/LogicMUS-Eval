"""Hash-checked table-only plots; CSV conversion stops at this typed boundary."""

import csv
import math
import textwrap
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from pydantic import BaseModel, ConfigDict, TypeAdapter

from logicmus_eval.analysis.artifacts import publication, verify_artifacts
from logicmus_eval.analysis.models import (
    AnalysisDiagnostics,
    AnalysisDimensions,
    AnalysisManifest,
    ConfidenceInterval,
)
from logicmus_eval.analysis.plan import Metric
from logicmus_eval.analysis.tables import DIMENSIONS
from logicmus_eval.models.evaluation import SeriesKind

plt.switch_backend("Agg")

METRIC_LABELS: dict[Metric, str] = {
    "mus_exact_match": "MUS Exact Match",
    "mus_f1": "Macro MUS F1",
    "sat_accuracy": "SAT accuracy",
    "coverage": "Valid-response coverage",
}
Axis = Literal["K", "N", "topology"]
DIMENSION_ADAPTER = TypeAdapter(AnalysisDimensions)
INTERVAL_ADAPTER = TypeAdapter(ConfidenceInterval)
FRACTIONS = TypeAdapter(dict[str, float])


@dataclass(frozen=True)
class PlotSummary:
    dimensions: AnalysisDimensions
    values: dict[Metric, float | None]
    intervals: dict[Metric, ConfidenceInterval]
    error_fractions: dict[str, float]


class PlotContrast(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str
    metric: Metric
    estimate: float
    low: float | None
    high: float | None
    degenerate: bool | None
    status: Literal["ok", "unavailable"]


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _summaries(root: Path, metrics: list[Metric]) -> list[PlotSummary]:
    result = []
    for raw in _read(root / "summary.csv"):
        dimensions = DIMENSION_ADAPTER.validate_python(
            {
                **{key: raw[key] for key in DIMENSIONS if key not in {"K", "N"}},
                "k": raw["K"],
                "n": raw["N"],
            }
        )
        values, intervals = {}, {}
        for metric in metrics:
            value = raw.get(metric, "")
            values[metric] = float(value) if value else None
            prefix = metric + "_ci_"
            fields = {
                key.removeprefix(prefix): value or None
                for key, value in raw.items()
                if key.startswith(prefix) and (key != prefix + "method" or value)
            }
            intervals[metric] = INTERVAL_ADAPTER.validate_python(fields)
        if "coverage" not in values:
            values["coverage"] = float(raw["coverage"]) if raw["coverage"] else None
        result.append(
            PlotSummary(
                dimensions,
                values,
                intervals,
                FRACTIONS.validate_json(raw["error_bucket_fractions"]),
            )
        )
    return result


def _save(fig: Figure, path: Path) -> None:
    try:
        fig.tight_layout()
        fig.savefig(path, dpi=150, bbox_inches="tight")
    finally:
        plt.close(fig)


def _facet(row: PlotSummary, axis: Axis) -> tuple[str, ...]:
    d = row.dimensions
    fixed = (d.group, d.purpose, d.series_id, d.model_id)
    if axis == "K":
        return (*fixed, f"N={d.n}", d.pattern_id)
    if axis == "N":
        return (*fixed, f"K={d.k}", d.pattern_id)
    return (*fixed, f"N={d.n}")


def _x(row: PlotSummary, axis: Axis, labels: list[str]) -> int:
    d = row.dimensions
    if axis == "topology":
        return labels.index(f"{d.pattern_id} (K={d.k})")
    return d.k if axis == "K" else d.n


KINDS: dict[Axis, SeriesKind] = {
    "N": "noise_sweep",
    "K": "k_sweep",
    "topology": "topology_panel",
}


def _draw_points(
    ax: Axes,
    rows: list[PlotSummary],
    metric: Metric,
    positions: Mapping[AnalysisDimensions, float],
) -> None:
    for number, strategy in enumerate(
        sorted({row.dimensions.strategy for row in rows})
    ):
        selected = sorted(
            [row for row in rows if row.dimensions.strategy == strategy],
            key=lambda row: positions[row.dimensions],
        )
        for point, row in enumerate(selected):
            value = row.values[metric]
            if value is None:
                continue
            x = positions[row.dimensions] + number * 0.06
            interval = row.intervals[metric]
            low, high = interval["low"], interval["high"]
            ax.plot(
                x,
                value,
                "o",
                color=f"C{number}",
                label=strategy if point == 0 else None,
            )
            if low is not None and high is not None:
                ax.vlines(x, low, high, color=f"C{number}", linewidth=1.5)
                ax.plot([x, x], [low, high], "_", color=f"C{number}")
            flag = (
                "CI n/a"
                if interval["status"] == "unavailable"
                else "degenerate"
                if interval["degenerate"]
                else None
            )
            if flag:
                ax.annotate(
                    flag,
                    (x, value),
                    xytext=(3, 6 if value < 0.8 else -12),
                    textcoords="offset points",
                    fontsize=7,
                    color=f"C{number}",
                )


def _quality_panel(
    ax: Axes, cell: list[PlotSummary], axis: Axis, metric: Metric, level: float
) -> None:
    labels = (
        sorted({f"{r.dimensions.pattern_id} (K={r.dimensions.k})" for r in cell})
        if axis == "topology"
        else []
    )
    positions = {row.dimensions: float(_x(row, axis, labels)) for row in cell}
    _draw_points(ax, cell, metric, positions)
    if labels:
        ax.set_xticks(range(len(labels)), labels, rotation=20, ha="right")
    ax.set_title(
        "\n".join(textwrap.wrap(" | ".join(_facet(cell[0], axis)), width=85)),
        fontsize=9,
    )
    ax.set_xlabel("Pattern and actual K" if axis == "topology" else axis)
    method = "Wilson" if metric == "mus_exact_match" else "family cluster bootstrap"
    ax.set_ylabel(f"{METRIC_LABELS[metric]}\n{level:.0%} pointwise {method}")
    ax.set_ylim(-0.04, 1.04)
    ax.grid(axis="y", alpha=0.2)
    ax.legend(fontsize=8)


def _quality(
    rows: list[PlotSummary], axis: Axis, metric: Metric, destination: Path, level: float
) -> None:
    facets: dict[tuple[str, ...], list[PlotSummary]] = defaultdict(list)
    for row in rows:
        if row.dimensions.series_kind == KINDS[axis]:
            facets[_facet(row, axis)].append(row)
    count = max(1, len(facets))
    columns = min(2, count)
    fig, axes = plt.subplots(
        math.ceil(count / columns),
        columns,
        squeeze=False,
        figsize=(7 * columns, 4 * math.ceil(count / columns)),
    )
    flat = list(axes.flat)
    if not facets:
        flat[0].text(0.5, 0.5, "No selected cells in this series", ha="center")
    for index, cell in enumerate(facets[key] for key in sorted(facets)):
        _quality_panel(flat[index], cell, axis, metric, level)
    for unused in flat[len(facets) if facets else 1 :]:
        unused.set_visible(False)
    _save(fig, destination)


def _coverage(rows: list[PlotSummary], destination: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(max(9, len(rows) * 0.6), 8), sharex=True)
    labels = []
    for index, row in enumerate(rows):
        d = row.dimensions
        labels.append(
            f"{d.group} / {d.series_id} / {d.pattern_id} / "
            f"{d.k} / {d.n} / {d.model_id} / {d.strategy}"
        )
        if (coverage := row.values.get("coverage")) is not None:
            axes[0].bar(index, coverage, color="C0")
    names = sorted({name for row in rows for name in row.error_fractions})
    bottom = [0.0] * len(rows)
    for name in names:
        values = [row.error_fractions.get(name, 0.0) for row in rows]
        axes[1].bar(range(len(rows)), values, bottom=bottom, label=name)
        bottom = [a + b for a, b in zip(bottom, values)]
    axes[0].set_ylabel("Valid-response coverage\n(all reference cases)")
    axes[1].set_ylabel("Exclusive outcome fractions\n(all reference cases)")
    axes[1].set_xticks(range(len(labels)), labels, rotation=70, ha="right", fontsize=7)
    if names:
        axes[1].legend(fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1))
    for ax in axes:
        ax.set_ylim(0, 1.05)
    _save(fig, destination)


def _contrasts(rows: list[PlotContrast], destination: Path, level: float) -> None:
    fig, ax = plt.subplots(figsize=(9, max(3, len(rows) * 0.65)))
    for index, row in enumerate(rows):
        ax.plot(row.estimate, index, "o", color="C0")
        if row.low is not None and row.high is not None:
            ax.hlines(index, row.low, row.high, color="C0")
    labels = [
        f"{r.name} ({r.metric})"
        + (" [degenerate]" if r.degenerate else "")
        + (" [CI unavailable]" if r.status == "unavailable" else "")
        for r in rows
    ]
    ax.set_yticks(range(len(rows)), labels)
    ax.axvline(0, color="gray", linestyle="--", linewidth=0.8)
    ax.set_xlabel(
        f"Paired right minus left; pointwise {level:.0%} family cluster percentile interval"
    )
    if not rows:
        ax.text(0.5, 0.5, "No planned contrasts", transform=ax.transAxes, ha="center")
    _save(fig, destination)


def _render(root: Path, manifest: AnalysisManifest) -> None:
    metrics = list(
        dict.fromkeys([manifest.plan.primary_metric, *manifest.plan.additional_metrics])
    )
    # Coverage is always exported even when no CI for it was requested.
    rows = _summaries(root, metrics)
    contrasts = [
        PlotContrast.model_validate({key: value or None for key, value in raw.items()})
        for raw in _read(root / "contrasts.csv")
    ]
    figures = root / "figures"
    figures.mkdir(exist_ok=True)
    sweeps: list[tuple[SeriesKind, Axis]] = [
        ("noise_sweep", "N"),
        ("k_sweep", "K"),
        ("topology_panel", "topology"),
    ]
    for kind, axis in sweeps:
        for metric in metrics:
            _quality(
                rows,
                axis,
                metric,
                figures / f"{kind}_{metric}.png",
                manifest.methods.level,
            )
    _coverage(rows, figures / "coverage_errors.png")
    _contrasts(contrasts, figures / "paired_differences.png", manifest.methods.level)


def plot_tables(root: Path, *, finalize: bool = True) -> None:
    """Standalone redraw publishes its state; service retains its outer transaction."""
    manifest = AnalysisManifest.model_validate_json(
        (root / "analysis.manifest.json").read_bytes()
    )
    if manifest.plan.mode != "primary" or (finalize and manifest.status != "complete"):
        raise ValueError("Only completed primary analysis tables can be plotted")
    verify_artifacts(root, manifest)
    if not finalize:
        if manifest.status != "running" or not manifest.plots_requested:
            raise ValueError("Rendering requires an active publication")
        _render(root, manifest)
        return
    diagnostics = AnalysisDiagnostics.model_validate_json(
        (root / "diagnostics.json").read_bytes()
    )
    manifest.plots_requested = True
    with publication(root, manifest, diagnostics):
        _render(root, manifest)
