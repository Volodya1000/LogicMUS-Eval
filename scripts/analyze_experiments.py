"""Analyze LogicMUS-Eval overnight-grid results.

Reads experiments/<timestamp>_overnight_grid/manifest.json, builds
summary.csv and details.csv, and saves plots into plots/.
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

# Терминология для графиков (соответствует тексту статьи)
METRIC_NAMES = {
    "sat_accuracy": "Точность определения статуса (SAT Accuracy)",
    "mus_f1": "F1-мера ядра конфликта",
    "mus_exact_match": "Доля точного совпадения (Exact Match)",
    "mus_precision": "Точность (Precision) элементов ядра",
    "mus_recall": "Полнота (Recall) элементов ядра",
    "infrastructure_error_rate": "Доля ошибок кодогенерации"
}

STRATEGY_NAMES = {
    "direct": "Прямой LLM-подход",
    "z3": "Нейросимвольный (Z3)"
}

def clean_model_name(name: str) -> str:
    if "qwen2.5-coder" in name.lower():
        return "Qwen2.5-Coder"
    elif "gemma-4" in name.lower():
        return "Gemma-4"
    elif "gpt-oss" in name.lower():
        return "GPT-OSS"
    return name.rsplit("/", maxsplit=1)[-1]

def _load_rows(root: Path) -> tuple[list[dict], list[dict]]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    rows, details = [], []

    for item in manifest:
        if item.get("type") != "report":
            continue
        report = Path(item["report"])
        if not report.exists():
            continue

        data = json.loads(report.read_text(encoding="utf-8"))
        cfg = item["config"]

        # Подсчет ошибок кодогенерации
        infra_errors = data.get("metrics", {}).get("infra_error_count", 0)
        total_eval = data.get("metrics", {}).get("total_evaluated", 1)
        error_rate = infra_errors / total_eval if total_eval > 0 else 0

        rows.append({
            "config": cfg["name"],
            "exp": cfg["exp"],
            "mus_size": cfg["mus_size"],
            "total_rules": cfg["total_rules"],
            "model": clean_model_name(item["model_label"] if "model_label" in item else item["model"]),
            "strategy": STRATEGY_NAMES.get(item["strategy"], item["strategy"]),
            "infrastructure_error_rate": error_rate,
            **data.get("metrics", {}),
        })

    return rows, details

def _plot_experiment(df: pd.DataFrame, exp: str, plot_dir: Path) -> None:
    sub = df[df["exp"] == exp]
    if sub.empty:
        return

    # Настраиваем ось X в зависимости от эксперимента
    if exp == "exp1_total_rules":
        x_col = "total_rules"
        x_label = "Общее количество требований (N)"
    elif exp == "exp2_mus_size":
        x_col = "mus_size"
        x_label = "Кардинальность ядра конфликта (K)"
    else:
        x_col = "mus_size"
        x_label = "Кардинальность ядра конфликта (K) [Стресс-тест]"

    metrics_to_plot = list(METRIC_NAMES.keys())

    # Цвета для моделей и стили линий для стратегий
    colors = {"Qwen2.5-Coder": "#1f77b4", "Gemma-4": "#ff7f0e", "GPT-OSS": "#2ca02c"}
    line_styles = {"Прямой LLM-подход": "--", "Нейросимвольный (Z3)": "-"}
    markers = {"Прямой LLM-подход": "x", "Нейросимвольный (Z3)": "o"}

    for metric in metrics_to_plot:
        if metric not in sub.columns:
            continue

        plt.figure(figsize=(9, 6))

        for (model, strategy), g in sub.groupby(["model", "strategy"]):
            g = g.sort_values(x_col)
            c = colors.get(model, "black")
            ls = line_styles.get(strategy, "-")
            mk = markers.get(strategy, "o")

            plt.plot(
                g[x_col],
                g[metric],
                marker=mk,
                color=c,
                linestyle=ls,
                linewidth=2,
                markersize=6,
                label=f"{model} ({strategy})",
            )

        plt.xlabel(x_label, fontsize=12)
        plt.ylabel(METRIC_NAMES[metric], fontsize=12)
        plt.title(f"{METRIC_NAMES[metric]}", fontsize=14)
        plt.grid(True, alpha=0.4, linestyle="--")
        plt.legend(fontsize=10, loc='best')
        plt.tight_layout()
        plt.savefig(plot_dir / f"{exp}_{metric}.png", dpi=300)
        plt.close()

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze.py experiments/<timestamp>_overnight_grid")
        sys.exit(1)

    root = Path(sys.argv[1])
    rows, _ = _load_rows(root)
    df = pd.DataFrame(rows)

    summary_path = root / "summary.csv"
    df.to_csv(summary_path, index=False)

    plot_dir = root / "plots"
    plot_dir.mkdir(exist_ok=True)

    for exp in df["exp"].unique():
        _plot_experiment(df, exp, plot_dir)

    print(f"Готово. Графики сохранены в: {plot_dir}")

if __name__ == "__main__":
    main()