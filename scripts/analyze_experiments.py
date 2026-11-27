"""Analyze LogicMUS-Eval overnight-grid results.

Reads experiments/<timestamp>_overnight_grid/manifest.json, builds
summary.csv and details.csv, and saves plots into plots/.
"""

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from pydantic import JsonValue, TypeAdapter

from logicmus_eval.evaluation.reports import (
    ReportManifestEntry,
    report_is_complete,
    require_completed_report,
)

plt.switch_backend("Agg")

# Терминология для графиков (соответствует тексту статьи)
METRIC_NAMES = {
    "sat_accuracy": "Точность определения статуса (SAT Accuracy)",
    "mus_f1": "F1-мера ядра конфликта",
    "mus_exact_match": "Доля точного совпадения (Exact Match)",
    "mus_precision": "Точность (Precision) элементов ядра",
    "mus_recall": "Полнота (Recall) элементов ядра",
    "infrastructure_error_rate": "Доля инфраструктурных ошибок API",
    "response_error_rate": "Доля ошибок ответа LLM",
    "execution_error_rate": "Доля ошибок исполнения кода",
}

STRATEGY_NAMES = {"direct": "Прямой LLM-подход", "z3": "Нейросимвольный (Z3)"}


def clean_model_name(name: str) -> str:
    if "qwen2.5-coder" in name.lower():
        return "Qwen2.5-Coder"
    if "gemma-4" in name.lower():
        return "Gemma-4"
    if "gpt-oss" in name.lower():
        return "GPT-OSS"
    return name.rsplit("/", maxsplit=1)[-1]


def _load_rows(
    root: Path,
) -> tuple[list[dict[str, JsonValue]], list[dict[str, JsonValue]]]:
    manifest = TypeAdapter(list[JsonValue]).validate_json(
        (root / "manifest.json").read_text(encoding="utf-8")
    )
    rows: list[dict[str, JsonValue]] = []

    for item in manifest:
        if not isinstance(item, dict) or item.get("type") != "report":
            continue
        entry = ReportManifestEntry.model_validate(item)
        limit = entry.config.pairs * 2 if entry.config.pairs is not None else None
        if not report_is_complete(
            entry.report, expected_cases=entry.planned, limit=limit
        ):
            continue

        data = require_completed_report(
            entry.report, expected_cases=entry.planned, limit=limit
        )
        cfg = entry.config

        # Подсчет ошибок кодогенерации
        infra_errors = data.metrics.get("infra_error_count")
        total_eval = data.metrics.get("total_evaluated")
        error_rate = (
            infra_errors / total_eval
            if isinstance(infra_errors, (int, float))
            and isinstance(total_eval, (int, float))
            and total_eval > 0
            else None
        )

        rows.append(
            {
                "config": cfg.name,
                "exp": cfg.exp,
                "mus_size": cfg.mus_size,
                "total_rules": cfg.total_rules,
                "model": clean_model_name(entry.model_label or entry.model),
                "strategy": STRATEGY_NAMES.get(entry.strategy, entry.strategy),
                "infrastructure_error_rate": error_rate,
                **data.metrics,
                "report_schema_version": data.report_schema_version,
                "metric_definitions_version": data.metric_definitions_version,
                "status": data.status,
            }
        )

    return rows, []


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

    # Цвета для моделей и стили линий для стратегий
    colors = {"Qwen2.5-Coder": "#1f77b4", "Gemma-4": "#ff7f0e", "GPT-OSS": "#2ca02c"}
    line_styles = {"Прямой LLM-подход": "--", "Нейросимвольный (Z3)": "-"}
    markers = {"Прямой LLM-подход": "x", "Нейросимвольный (Z3)": "o"}

    for metric, default_label in METRIC_NAMES.items():
        if metric not in sub.columns:
            continue

        plt.figure(figsize=(9, 6))

        for (model, strategy), g in sub.groupby(["model", "strategy"]):
            model, strategy = str(model), str(strategy)
            g = g.sort_values(x_col)
            plt.plot(
                g[x_col],
                g[metric],
                marker=markers.get(strategy, "o"),
                color=colors.get(model, "black"),
                linestyle=line_styles.get(strategy, "-"),
                linewidth=2,
                markersize=6,
                label=f"{model} ({strategy})",
            )

        plt.xlabel(x_label, fontsize=12)
        label = default_label
        if (
            metric == "infrastructure_error_rate"
            and not (sub["metric_definitions_version"] == "3").all()
        ):
            label = "Доля ошибок (старое объединенное определение)"
        plt.ylabel(label, fontsize=12)
        plt.title(label, fontsize=14)
        plt.grid(True, alpha=0.4, linestyle="--")
        plt.legend(fontsize=10, loc="best")
        plt.tight_layout()
        plt.savefig(plot_dir / f"{exp}_{metric}.png", dpi=300)
        plt.close()


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/analyze.py experiments/<timestamp>_overnight_grid")
        sys.exit(1)

    root = Path(sys.argv[1])
    rows, _ = _load_rows(root)
    df = (
        pd.DataFrame(rows)
        if rows
        else pd.DataFrame(
            columns=[
                "config",
                "exp",
                "mus_size",
                "total_rules",
                "model",
                "strategy",
                "metric_definitions_version",
                "report_schema_version",
                *METRIC_NAMES,
            ]
        )
    )
    for metric in METRIC_NAMES:
        if metric in df:
            df[metric] = pd.to_numeric(df[metric], errors="raise")

    summary_path = root / "summary.csv"
    df.to_csv(summary_path, index=False)

    plot_dir = root / "plots"
    plot_dir.mkdir(exist_ok=True)

    versions = df["metric_definitions_version"].fillna("legacy").astype(str)
    for version in versions.unique():
        selected = df[versions == version]
        destination = (
            plot_dir / f"metrics_{version}" if versions.nunique() > 1 else plot_dir
        )
        destination.mkdir(exist_ok=True)
        for exp in selected["exp"].unique():
            _plot_experiment(selected, str(exp), destination)

    print(f"Готово. Графики сохранены в: {plot_dir}")


if __name__ == "__main__":
    main()
