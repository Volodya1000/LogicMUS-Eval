"""Analyze Exact Match by Pattern (Topology) for UNSAT cases.

Usage:
    uv run python scripts/analyze_patterns.py experiments/<timestamp>_overnight_grid
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib
from matplotlib.axes import Axes

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # pylint: disable=wrong-import-position
import numpy as np  # pylint: disable=wrong-import-position
import pandas as pd  # pylint: disable=wrong-import-position
from numpy.typing import NDArray  # pylint: disable=wrong-import-position

STRATEGY_NAMES = {"direct": "Прямой LLM-подход", "z3": "Нейросимвольный (Z3)"}

# Маппинг внутренних названий паттернов на русские термины из статьи
PATTERN_NAMES = {
    "pack_00": "Прямое\nпротиворечие",
    "pack_01": "Транзитивная\nцепочка",
    "pack_02": "Ветвление",
    "pack_03": "Конвергентный\nконфликт",
    "pack_04": "Покрытие\nвариантов",
    "math_pack": "Математический\nцикл",
}


@dataclass
class PlotContext:
    """Общий контекст для построения графиков по всем моделям."""

    patterns: list[str]
    display_labels: list[str]
    strategies: list[str]
    colors: dict[str, str]
    plot_dir: Path


def clean_model_name(name: str) -> str:
    if "qwen" in name.lower():
        return "Qwen2.5-Coder"
    if "gemma" in name.lower():
        return "Gemma-4"
    if "gpt-oss" in name.lower():
        return "GPT-OSS"
    return name.rsplit("/", maxsplit=1)[-1]


def _build_case_to_pattern(manifest: list[dict[str, Any]]) -> dict[str, str]:
    """Сопоставляет case_id -> паттерн для UNSAT-кейсов."""
    case_to_pattern: dict[str, str] = {}
    dataset_paths = {
        item["dataset"] for item in manifest if item.get("type") == "report"
    }

    for dp in dataset_paths:
        dpath = Path(dp)
        if not dpath.exists():
            continue
        with open(dpath, "r", encoding="utf-8") as f:
            for line in f:
                case = json.loads(line)
                if case.get("is_satisfiable", True):
                    continue
                meta = case.get("metadata", {})
                # Ищем паттерн по разным возможным ключам
                pattern = (
                    meta.get("topology")
                    or meta.get("pattern")
                    or case.get("template_pack_id")
                    or "Unknown"
                )
                case_to_pattern[case["case_id"]] = pattern

    return case_to_pattern


def _collect_records(
    manifest: list[dict[str, Any]], case_to_pattern: dict[str, str]
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in manifest:
        if item.get("type") != "report":
            continue

        report_path = Path(item["report"])
        if not report_path.exists():
            continue

        data = json.loads(report_path.read_text(encoding="utf-8"))
        model = clean_model_name(item.get("model_label", item["model"]))
        strategy = STRATEGY_NAMES.get(item["strategy"], item["strategy"])

        for d in data.get("details", []):
            if d["expected_sat"]:  # Только UNSAT (с конфликтом)
                continue
            cid = d["case_id"]
            records.append(
                {
                    "model": model,
                    "strategy": strategy,
                    "case_id": cid,
                    "pattern": case_to_pattern.get(cid, "Unknown"),
                    "is_mus_correct": 1 if d.get("is_mus_correct") else 0,
                }
            )

    return records


def load_data(root: Path) -> pd.DataFrame:
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"No manifest.json in {root}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    case_to_pattern = _build_case_to_pattern(manifest)
    return pd.DataFrame(_collect_records(manifest, case_to_pattern))


def _y_values_for_strategy(
    strat_data: pd.DataFrame, patterns: list[str]
) -> list[float]:
    y_values: list[float] = []
    for p in patterns:
        val = strat_data[strat_data["pattern"] == p]["is_mus_correct"]
        y_values.append(val.values[0] if not val.empty else 0.0)
    return y_values


def _draw_bars(
    ax: Axes,
    model_df: pd.DataFrame,
    patterns: list[str],
    strategies: list[str],
    colors: dict[str, str],
) -> NDArray[np.int_]:
    """Рисует сгруппированные столбцы и возвращает x-координаты."""
    x = np.arange(len(patterns))
    width = 0.35

    for i, strat in enumerate(strategies):
        strat_data = model_df[model_df["strategy"] == strat]
        y_values = _y_values_for_strategy(strat_data, patterns)
        offset = (i - len(strategies) / 2 + 0.5) * width
        ax.bar(
            x + offset,
            y_values,
            width,
            label=strat,
            color=colors.get(strat, "gray"),
            zorder=3,
        )

    return x


def _plot_model(model: str, model_df: pd.DataFrame, ctx: PlotContext) -> Path:
    _, ax = plt.subplots(figsize=(10, 5))
    x = _draw_bars(ax, model_df, ctx.patterns, ctx.strategies, ctx.colors)

    ax.set_ylabel("Доля точного совпадения (Exact Match)", fontsize=12)
    ax.set_title(
        f"Точность локализации конфликта по типам паттернов: {model}", fontsize=14
    )
    ax.set_xticks(x)
    ax.set_xticklabels(ctx.display_labels, rotation=0, fontsize=10)
    ax.set_ylim(0, 1.05)

    ax.legend(
        title="Стратегия", loc="upper center", bbox_to_anchor=(0.5, -0.15), ncol=2
    )
    ax.grid(axis="y", linestyle="--", alpha=0.7, zorder=0)

    plt.tight_layout()
    safe_model_name = model.lower().replace(".", "_").replace("-", "_")
    plot_path = ctx.plot_dir / f"pattern_comparison_{safe_model_name}.png"

    plt.savefig(plot_path, dpi=300, bbox_inches="tight")
    plt.close()
    return plot_path


def _print_summary(summary: pd.DataFrame, plot_dir: Path) -> None:
    csv_path = plot_dir / "patterns_summary.csv"
    summary.to_csv(csv_path, index=False)

    print(f"\nДанные по паттернам успешно собраны и сохранены в: {csv_path}")
    print("\n" + "=" * 40)
    print("СКОПИРУЙТЕ ТЕКСТ НИЖЕ И ОТПРАВЬТЕ МНЕ:")
    print("=" * 40)
    print(summary.to_csv(index=False))
    print("=" * 40 + "\n")


def _build_plot_context(summary: pd.DataFrame, plot_dir: Path) -> PlotContext:
    # Сортируем паттерны по алфавиту (или номеру пака),
    # чтобы порядок на всех графиках был одинаковый
    patterns = sorted(summary["pattern"].unique())
    display_labels = [PATTERN_NAMES.get(p, p) for p in patterns]
    strategies = sorted(summary["strategy"].unique())  # Прямой подход, затем Z3
    colors = {"Прямой LLM-подход": "#ff7f0e", "Нейросимвольный (Z3)": "#1f77b4"}
    return PlotContext(patterns, display_labels, strategies, colors, plot_dir)


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Usage: python scripts/analyze_patterns.py "
            "experiments/<timestamp>_overnight_grid"
        )
        sys.exit(1)

    root = Path(sys.argv[1])
    df = load_data(root)

    if df.empty:
        print("No UNSAT data found.")
        sys.exit(0)

    summary = (
        df.groupby(["pattern", "model", "strategy"])["is_mus_correct"]
        .mean()
        .reset_index()
    )

    plot_dir = root / "plots"
    plot_dir.mkdir(exist_ok=True)

    _print_summary(summary, plot_dir)

    ctx = _build_plot_context(summary, plot_dir)

    # Генерируем отдельный график для каждой модели
    for model in summary["model"].unique():
        model_df = summary[summary["model"] == model]
        plot_path = _plot_model(model, model_df, ctx)
        print(f"График сохранен: {plot_path}")


if __name__ == "__main__":
    main()
