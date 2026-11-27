"""Figures consume exported tables only. No raw reports or metric reconstruction."""
# pylint: disable=too-many-locals

import csv
import json
import math
import textwrap
from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.axes import Axes

from logicmus_eval.analysis.tables import DIMENSIONS
from logicmus_eval.hashing import compute_file_sha256

plt.switch_backend("Agg")

METRIC_LABELS = {
    "mus_exact_match": "MUS Exact Match",
    "mus_f1": "Macro MUS F1",
    "sat_accuracy": "SAT accuracy",
    "coverage": "Valid-response coverage",
}


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def _save(fig: Any, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _quality(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    rows: list[dict[str, str]],
    kind: str,
    axis: str,
    metric: str,
    destination: Path,
    level: float,
) -> None:
    facets: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    fixed = ["group", "purpose", "series_id", "model_id"]
    fixed += ["N"] if axis == "K" else ["K"] if axis == "N" else ["N"]
    if axis != "topology":
        fixed.append("pattern_id")
    for row in rows:
        if row["series_kind"] == kind:
            facets[tuple(row[key] for key in fixed)].append(row)
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
    for index, (key, cell) in enumerate(sorted(facets.items())):
        ax: Axes = flat[index]
        labels = (
            sorted({f"{r['pattern_id']} (K={r['K']})" for r in cell})
            if axis == "topology"
            else []
        )
        strategies = sorted({row["strategy"] for row in cell})
        for number, strategy in enumerate(strategies):
            selected = [
                row
                for row in cell
                if row["strategy"] == strategy and row.get(metric, "") != ""
            ]
            for point, row in enumerate(
                sorted(
                    selected,
                    key=lambda r: (
                        int(r[axis]) if axis != "topology" else r["pattern_id"],
                        int(r["K"]),
                    ),
                )
            ):
                x = (
                    labels.index(f"{row['pattern_id']} (K={row['K']})")
                    if axis == "topology"
                    else int(row[axis])
                ) + number * 0.06
                value = float(row[metric])
                low, high = row.get(f"{metric}_ci_low"), row.get(f"{metric}_ci_high")
                ax.plot(
                    x,
                    value,
                    "o",
                    color=f"C{number}",
                    label=strategy if point == 0 else None,
                )
                if low and high:
                    ax.vlines(
                        x, float(low), float(high), color=f"C{number}", linewidth=1.5
                    )
                    ax.plot([x, x], [float(low), float(high)], "_", color=f"C{number}")
                flag = (
                    "CI n/a"
                    if row.get(f"{metric}_ci_status") == "unavailable"
                    else "degenerate"
                    if row.get(f"{metric}_ci_degenerate") == "True"
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
        if labels:
            ax.set_xticks(range(len(labels)), labels, rotation=20, ha="right")
        title = " | ".join(f"{name}={value}" for name, value in zip(fixed, key))
        ax.set_title("\n".join(textwrap.wrap(title, width=85)), fontsize=9)
        ax.set_xlabel("Pattern and actual K" if axis == "topology" else axis)
        method = "Wilson" if metric == "mus_exact_match" else "family cluster bootstrap"
        ax.set_ylabel(f"{METRIC_LABELS[metric]}\n{level:.0%} pointwise {method}")
        ax.set_ylim(-0.04, 1.04)
        ax.grid(axis="y", alpha=0.2)
        if strategies:
            ax.legend(fontsize=8)
    for unused in flat[len(facets) if facets else 1 :]:
        unused.set_visible(False)
    _save(fig, destination)


def _coverage(rows: list[dict[str, str]], destination: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(max(9, len(rows) * 0.6), 8), sharex=True)
    labels = [
        " / ".join(
            row[key] for key in DIMENSIONS if key not in {"purpose", "series_kind"}
        )
        for row in rows
    ]
    for index, row in enumerate(rows):
        if row.get("coverage", "") != "":
            axes[0].bar(index, float(row["coverage"]), color="C0")
    buckets = [json.loads(row["error_bucket_fractions"]) for row in rows]
    names = sorted({name for counts in buckets for name in counts})
    bottom = [0.0] * len(rows)
    for name in names:
        values = [counts.get(name, 0.0) for counts in buckets]
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


def _contrasts(rows: list[dict[str, str]], destination: Path, level: float) -> None:
    fig, ax = plt.subplots(figsize=(9, max(3, len(rows) * 0.65)))
    for index, row in enumerate(rows):
        ax.plot(float(row["estimate"]), index, "o", color="C0")
        if row["low"] and row["high"]:
            ax.hlines(index, float(row["low"]), float(row["high"]), color="C0")
    labels = [
        f"{r['name']} ({r['metric']})"
        + (" [degenerate]" if r.get("degenerate") == "True" else "")
        + (" [CI unavailable]" if r.get("status") == "unavailable" else "")
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


def plot_tables(root: Path) -> None:
    """Check table hashes, then draw sparse points; missing cells are never joined."""
    manifest = json.loads((root / "analysis.manifest.json").read_text(encoding="utf-8"))
    if manifest["status"] != "complete" or manifest["plan"]["mode"] != "primary":
        raise ValueError("Only completed primary analysis tables can be plotted")
    for name, checksum in manifest["artifacts"].items():
        if compute_file_sha256(root / name) != checksum:
            raise ValueError(f"Analysis table changed: {name}")
    rows = _read(root / "summary.csv")
    contrasts = _read(root / "contrasts.csv")
    figures = root / "figures"
    figures.mkdir(exist_ok=True)
    level = manifest["methods"]["level"]
    for kind, axis in [
        ("noise_sweep", "N"),
        ("k_sweep", "K"),
        ("topology_panel", "topology"),
    ]:
        for metric in dict.fromkeys(
            [
                manifest["plan"]["primary_metric"],
                *manifest["plan"]["additional_metrics"],
            ]
        ):
            _quality(rows, kind, axis, metric, figures / f"{kind}_{metric}.png", level)
    _coverage(rows, figures / "coverage_errors.png")
    _contrasts(contrasts, figures / "paired_differences.png", level)
