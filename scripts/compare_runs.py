"""Build combined comparison plots from multiple quick-grid runs.

Usage:
    python scripts/compare_models.py \
        experiments/20260927_163316_quick_grid \
        experiments/20260927_183000_quick_grid \
        --output experiments/_combined

Each input directory must contain a `summary.csv` produced by
`scripts/analyze.py`. The script merges them and saves comparison
plots into the output directory.

Plots produced:
- mus_f1_vs_total_rules.png       (exp1, direct vs z3, per model)
- mus_f1_vs_mus_size.png          (exp2, direct vs z3, per model)
- sat_accuracy_vs_total_rules.png
- sat_accuracy_vs_mus_size.png
- mus_exact_match_vs_mus_size.png
- infra_error_rate_vs_mus_size.png
- heatmap_mus_f1.png              (model x strategy x config)
"""

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

METRICS = [
    "sat_accuracy",
    "mus_f1",
    "mus_exact_match",
    "mus_precision",
    "mus_recall",
    "infrastructure_error_rate",
]

# Pretty labels for the legend.
MODEL_LABELS = {
    "openai/qwen2.5-coder-14b-instruct": "Qwen2.5-Coder-14B",
    "openai/google/gemma-4-e4b": "Gemma-4-E4B",
    "openai/gpt-oss-20b": "GPT-OSS-20B",
}

# Line styles per strategy — solid for direct, dashed for z3.
STRATEGY_STYLES: dict[str, dict] = {
    "direct": {"linestyle": "-", "marker": "o", "markersize": 8, "markerfacecolor": "white", "markeredgewidth": 2},
    "z3":     {"linestyle": "--", "marker": "s", "markersize": 8, "markerfacecolor": "white", "markeredgewidth": 2},
}

# Colors per model — consistent across all plots.
MODEL_COLORS = {
    "Qwen2.5-Coder-14B": "#1f77b4",
    "Gemma-4-E4B": "#d62728",
    "GPT-OSS-20B": "#2ca02c",
}



# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_summaries(dirs: list[Path]) -> pd.DataFrame:
    """Load and concatenate summary.csv from each directory.

    Deduplicates on (config, model, strategy) keeping the first
    occurrence, so an older and a newer run of the same config don't
    produce two lines.
    """
    frames: list[pd.DataFrame] = []
    for d in dirs:
        summary = d / "summary.csv"
        if not summary.exists():
            print(f"[WARN] no summary.csv in {d}", file=sys.stderr)
            continue
        df = pd.read_csv(summary)
        df["_source"] = d.name
        frames.append(df)

    if not frames:
        raise SystemExit("No summary.csv found in any of the given directories.")

    merged = pd.concat(frames, ignore_index=True)
    merged["model_label"] = merged["model"].map(MODEL_LABELS).fillna(merged["model"])

    before = len(merged)
    merged = merged.drop_duplicates(
        subset=["config", "model", "strategy"], keep="first"
    ).reset_index(drop=True)
    after = len(merged)
    if before != after:
        print(f"[INFO] dropped {before - after} duplicate rows across runs")

    return merged


# ---------------------------------------------------------------------------
# Plotting helpers
# ---------------------------------------------------------------------------


def _line_plot(
    df: pd.DataFrame,
    exp: str,
    x_col: str,
    metric: str,
    out_path: Path,
) -> None:
    sub = df[df["exp"] == exp]
    if sub.empty:
        return

    fig, ax = plt.subplots(figsize=(9, 5.5))

    for (model_label, strategy), g in sub.groupby(["model_label", "strategy"]):
        g = g.sort_values(x_col)
        if metric not in g.columns:
            continue
        color = MODEL_COLORS.get(model_label, "gray")
        style = STRATEGY_STYLES.get(strategy, {"linestyle": ":", "marker": "x"})
        ax.plot(
            g[x_col],
            g[metric],
            label=f"{model_label} / {strategy}",
            color=color,
            linewidth=2,
            **style,
        )

    ax.set_xlabel(x_col.replace("_", " "))
    ax.set_ylabel(metric.replace("_", " "))
    ax.set_title(f"{metric} — {exp}")
    ax.grid(True, alpha=0.3)
    ax.set_ylim(-0.02, 1.05)
    ax.legend(fontsize=9, loc="best", numpoints=1, framealpha=0.9)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def _heatmap(
    df: pd.DataFrame,
    metric: str,
    out_path: Path,
) -> None:
    """Heatmap of metric across (config) rows and (model x strategy) cols."""
    if metric not in df.columns:
        return

    pivot = df.pivot_table(
        index="config",
        columns=["model_label", "strategy"],
        values=metric,
        aggfunc="mean",
    )
    if pivot.empty:
        return

    # Sort rows: exp1 first (mus3_*), then exp2 (mus2_, mus5_, mus10_), then exp3.
    def _row_key(name: str) -> tuple[int, int]:
        parts = name.split("_")
        mus = int(parts[0].replace("mus", ""))
        rules = int(parts[1].replace("total", ""))
        if name.startswith("mus3_") and rules in (10, 20, 30):
            return (0, rules)
        if name.startswith("mus15_"):
            return (2, mus)
        return (1, mus)

    pivot = pivot.reindex(sorted(pivot.index, key=_row_key))

    fig, ax = plt.subplots(figsize=(1.6 * pivot.shape[1] + 3, 0.6 * pivot.shape[0] + 2))
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", vmin=0.0, vmax=1.0)

    ax.set_xticks(range(pivot.shape[1]))
    ax.set_xticklabels(
        [f"{m}\n{s}" for m, s in pivot.columns],
        fontsize=8,
    )
    ax.set_yticks(range(pivot.shape[0]))
    ax.set_yticklabels(pivot.index, fontsize=9)
    ax.set_title(f"{metric} — heatmap (empty cells = missing data)")

    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            val = pivot.values[i, j]
            if pd.notna(val):
                ax.text(
                    j, i, f"{val:.2f}",
                    ha="center", va="center",
                    fontsize=8, color="black",
                )

    fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dirs",
        nargs="+",
        type=Path,
        help="One or more experiment directories with summary.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("experiments/_combined"),
        help="Output directory for combined plots (default: experiments/_combined)",
    )
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)

    df = load_summaries(args.dirs)

    # Persist the merged table for inspection.
    merged_csv = args.output / "combined_summary.csv"
    df.to_csv(merged_csv, index=False)
    print(f"[OK] merged summary: {merged_csv} ({len(df)} rows)")

    # Line plots for each experiment and metric.
    for exp, x_col in (
        ("exp1_total_rules", "total_rules"),
        ("exp2_mus_size", "mus_size"),
        ("exp3_stress", "mus_size"),
    ):
        if exp not in df["exp"].values:
            continue
        for metric in METRICS:
            out = args.output / f"{exp}_{metric}.png"
            _line_plot(df, exp, x_col, metric, out)
            print(f"[OK] {out.name}")

    # Heatmaps across all configurations.
    for metric in ("mus_f1", "sat_accuracy"):
        out = args.output / f"heatmap_{metric}.png"
        _heatmap(df, metric, out)
        print(f"[OK] {out.name}")

    print(f"\nAll plots saved to: {args.output}")


if __name__ == "__main__":
    main()