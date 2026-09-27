"""Analyze LogicMUS-Eval quick-grid results.

Reads experiments/<timestamp>_quick_grid/manifest.json, builds
summary.csv and details.csv, and saves plots into plots/.

Usage:
    uv run python scripts/analyze.py experiments/<timestamp>_quick_grid
"""

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

# matplotlib.use() must run before pyplot is imported.
import matplotlib.pyplot as plt  # pylint: disable=wrong-import-position
import pandas as pd  # pylint: disable=wrong-import-position

METRICS = ["sat_accuracy", "mus_f1", "mus_exact_match", "mus_precision", "mus_recall"]


def _load_rows(root: Path) -> tuple[list[dict], list[dict]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))

    rows: list[dict] = []
    details: list[dict] = []

    for item in manifest:
        if item.get("type") != "report":
            continue
        report = Path(item["report"])
        if not report.exists():
            continue

        data = json.loads(report.read_text(encoding="utf-8"))
        cfg = item["config"]

        rows.append(
            {
                "config": cfg["name"],
                "exp": cfg["exp"],
                "mus_size": cfg["mus_size"],
                "total_rules": cfg["total_rules"],
                "model": item["model"],
                "strategy": item["strategy"],
                **data.get("metrics", {}),
            }
        )

        for d in data.get("details", []):
            details.append(
                {
                    "config": cfg["name"],
                    "exp": cfg["exp"],
                    "mus_size": cfg["mus_size"],
                    "total_rules": cfg["total_rules"],
                    "model": item["model"],
                    "strategy": item["strategy"],
                    "case_id": d["case_id"],
                    "expected_sat": d["expected_sat"],
                    "predicted_sat": d.get("predicted_sat"),
                    "is_sat_correct": d["is_sat_correct"],
                    "is_mus_correct": d.get("is_mus_correct"),
                    "failure_tags": ",".join(d.get("failure_tags", [])),
                    "error": d.get("error"),
                }
            )

    return rows, details


def _plot_experiment(df: pd.DataFrame, exp: str, plot_dir: Path) -> None:
    sub = df[df["exp"] == exp]
    if sub.empty:
        return

    x_col = "total_rules" if exp == "exp1_total_rules" else "mus_size"

    for metric in METRICS:
        if metric not in sub.columns:
            continue

        plt.figure(figsize=(8, 5))
        for (model, strategy), g in sub.groupby(["model", "strategy"]):
            g = g.sort_values(x_col)
            model_name = str(model).rsplit("/", maxsplit=1)[-1]
            plt.plot(
                g[x_col],
                g[metric],
                marker="o",
                label=f"{model_name} / {strategy}",
            )

        plt.xlabel(x_col)
        plt.ylabel(metric)
        plt.title(f"{metric} вЂ” {exp}")
        plt.grid(True, alpha=0.3)
        plt.legend(fontsize=8)
        plt.tight_layout()
        plt.savefig(plot_dir / f"{exp}_{metric}.png", dpi=150)
        plt.close()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze.py experiments/<timestamp>_quick_grid")
        sys.exit(1)

    root = Path(sys.argv[1])
    if not (root / "manifest.json").exists():
        print(f"No manifest.json in {root}")
        sys.exit(1)

    rows, details = _load_rows(root)

    df = pd.DataFrame(rows)
    det = pd.DataFrame(details)

    summary_path = root / "summary.csv"
    details_path = root / "details.csv"
    df.to_csv(summary_path, index=False)
    det.to_csv(details_path, index=False)

    plot_dir = root / "plots"
    plot_dir.mkdir(exist_ok=True)

    for exp in df["exp"].unique():
        _plot_experiment(df, exp, plot_dir)

    print(f"summary: {summary_path}")
    print(f"details: {details_path}")
    print(f"plots:   {plot_dir}")


if __name__ == "__main__":
    main()
