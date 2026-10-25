"""Create reproducible article figures from frozen LogicMUS-Eval results.

The script consumes an existing experiment directory (``summary.csv`` and
``details.csv``) and never re-runs a model.  It reconstructs the generated
pattern label from the documented round-robin strategy registry used by
``logicmus_eval.run_pipeline.generate_dataset``.  The heatmap deliberately
keeps missing ``(K, N)`` cells empty: the stored benchmark is an L-shaped
grid, not a complete factorial design.

Usage:
    uv run --group analysis python scripts/make_article_figures.py \
        experiments/20260928_224011_overnight_grid \
        --output experiments/20260928_224011_overnight_grid/article_figures
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

STRATEGIES_BY_MUS_SIZE = {
    2: ["chain", "coverage", "direct", "fork", "idem", "merge", "math"],
    3: ["chain", "direct", "fork", "merge", "math"],
}
DEFAULT_STRATEGIES = ["chain", "direct", "fork", "merge", "math"]
PATTERN_LABELS = {
    "chain": "Транзитивная цепочка",
    "coverage": "Покрытие вариантов",
    "direct": "Прямое противоречие",
    "fork": "Ветвление",
    "idem": "Тождественность",
    "merge": "Конвергентный конфликт",
    "math": "Математический конфликт",
}
STRATEGY_LABELS = {"direct": "Прямой LLM", "z3": "LLM + Z3"}
MODEL_ORDER = ["Qwen2.5-Coder-14B", "Gemma-4-E4B", "GPT-OSS-20B"]
ERROR_LABELS = {
    "correct": "Корректно",
    "wrong_sat": "Неверный SAT/UNSAT",
    "wrong_mus_missing": "Потеря элементов MUS",
    "wrong_mus_extra": "Лишние элементы MUS",
    "exec_error": "Ошибка кодогенерации/исполнения",
}
ERROR_COLORS = {
    "correct": "#4daf4a",
    "wrong_sat": "#377eb8",
    "wrong_mus_missing": "#ff7f00",
    "wrong_mus_extra": "#984ea3",
    "exec_error": "#e41a1c",
}


def clean_model(name: str) -> str:
    lowered = name.lower()
    if "qwen2.5" in lowered:
        return "Qwen2.5-Coder-14B"
    if "gemma" in lowered:
        return "Gemma-4-E4B"
    if "gpt-oss" in lowered:
        return "GPT-OSS-20B"
    return name.rsplit("/", 1)[-1]


def pattern_for_case(case_id: str, mus_size: int) -> str:
    index = int(case_id.rsplit("_", 1)[-1])
    strategies = STRATEGIES_BY_MUS_SIZE.get(mus_size, DEFAULT_STRATEGIES)
    return strategies[index % len(strategies)]


def f1(expected: list[str], predicted: list[str]) -> float:
    expected_set = set(expected or [])
    predicted_set = set(predicted or [])
    if not expected_set and not predicted_set:
        return 1.0
    if not expected_set or not predicted_set:
        return 0.0
    overlap = len(expected_set & predicted_set)
    precision = overlap / len(predicted_set)
    recall = overlap / len(expected_set)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def load_data(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = pd.read_csv(root / "summary.csv")
    details_path = root / "details.csv"
    details = pd.read_csv(details_path) if details_path.exists() else pd.DataFrame()
    # Older overnight runs export only booleans in details.csv.  The report
    # JSONs contain the full expected/predicted MUS lists required for the
    # pattern-level F1 plot, so prefer them whenever those columns are absent.
    if "expected_mus" not in details.columns:
        import json

        rows: list[dict] = []
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        for item in manifest:
            if item.get("type") != "report" or item.get("status") != "ok":
                continue
            report_path = Path(item["report"])
            if not report_path.is_absolute():
                report_path = Path.cwd() / report_path
            if not report_path.exists():
                report_path = (
                    root / Path(item["report"]).relative_to(root)
                    if str(item["report"]).startswith(str(root))
                    else root / Path(item["report"]).name
                )
            if not report_path.exists():
                continue
            report = json.loads(report_path.read_text(encoding="utf-8"))
            cfg = item["config"]
            for item_detail in report.get("details", []):
                rows.append(
                    {
                        "config": cfg["name"],
                        "exp": cfg["exp"],
                        "mus_size": cfg["mus_size"],
                        "total_rules": cfg["total_rules"],
                        "model": item.get("model_label", item.get("model", "")),
                        "strategy": item["strategy"],
                        "case_id": item_detail["case_id"],
                        "expected_sat": item_detail["expected_sat"],
                        "predicted_sat": item_detail.get("predicted_sat"),
                        "failure_tags": ",".join(item_detail.get("failure_tags", [])),
                        "expected_mus": repr(item_detail.get("expected_mus", [])),
                        "predicted_mus": repr(item_detail.get("predicted_mus", [])),
                    }
                )
        details = pd.DataFrame(rows)
    summary["model"] = summary["model"].map(clean_model)
    details["model"] = details["model"].map(clean_model)
    details["pattern"] = [
        pattern_for_case(case_id, int(k))
        for case_id, k in zip(details["case_id"], details["mus_size"])
    ]
    return summary, details


def _save(fig: plt.Figure, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def plot_pattern_f1(details: pd.DataFrame, out: Path) -> None:
    unsat = details[details["expected_sat"] == False].copy()
    unsat["mus_f1"] = [
        f1([], []) if pd.isna(x) else 0.0 for x in unsat["predicted_mus"]
    ]
    # CSV details intentionally stores lists as strings; use report-level F1
    # only for aggregate plots when parsing is unavailable.  Recompute from
    # the serialized list values for exact per-case values.
    import ast

    unsat["mus_f1"] = [
        f1(ast.literal_eval(expected), ast.literal_eval(predicted))
        for expected, predicted in zip(unsat["expected_mus"], unsat["predicted_mus"])
    ]
    grouped = unsat.groupby(["pattern", "strategy"], as_index=False)["mus_f1"].mean()
    patterns = [p for p in PATTERN_LABELS if p in grouped["pattern"].unique()]
    x = np.arange(len(patterns))
    width = 0.36
    fig, ax = plt.subplots(figsize=(11, 5.8))
    for offset, strategy in zip([-width / 2, width / 2], ["direct", "z3"]):
        values = [
            grouped[(grouped.pattern == p) & (grouped.strategy == strategy)][
                "mus_f1"
            ].mean()
            for p in patterns
        ]
        ax.bar(x + offset, values, width, label=STRATEGY_LABELS[strategy])
    ax.set_xticks(x, [PATTERN_LABELS[p] for p in patterns], rotation=25, ha="right")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("F1-мера ядра конфликта")
    ax.set_title("Качество восстановления MUS по типу логического конфликта")
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    _save(fig, out / "fig_pattern_type_mus_f1.png")


def error_bucket(tags: str) -> str:
    tags_set = set(str(tags).split(","))
    if "exec_error" in tags_set:
        return "exec_error"
    if "wrong_sat" in tags_set:
        return "wrong_sat"
    if "wrong_mus_missing" in tags_set and "wrong_mus_extra" in tags_set:
        return "wrong_mus_missing"
    if "wrong_mus_missing" in tags_set:
        return "wrong_mus_missing"
    if "wrong_mus_extra" in tags_set:
        return "wrong_mus_extra"
    return "correct"


def plot_errors(details: pd.DataFrame, out: Path) -> None:
    frame = details.copy()
    frame["error"] = frame["failure_tags"].map(error_bucket)
    counts = frame.groupby(["model", "strategy", "error"]).size().unstack(fill_value=0)
    counts = counts.reindex(columns=list(ERROR_LABELS), fill_value=0)
    shares = counts.div(counts.sum(axis=1), axis=0)
    labels = [f"{m}\n{STRATEGY_LABELS[s]}" for m, s in shares.index]
    fig, ax = plt.subplots(figsize=(12, 6))
    bottom = np.zeros(len(shares))
    for error, error_label in ERROR_LABELS.items():
        values = shares[error].to_numpy()
        ax.bar(
            labels, values, bottom=bottom, label=error_label, color=ERROR_COLORS[error]
        )
        bottom += values
    ax.set_ylim(0, 1)
    ax.set_ylabel("Доля случаев")
    ax.set_title("Состав ошибок по модели и подходу")
    ax.tick_params(axis="x", labelsize=8)
    ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1))
    _save(fig, out / "fig_error_composition.png")


def plot_heatmap(details: pd.DataFrame, out: Path) -> None:
    import ast

    frame = details[details["expected_sat"] == False].copy()
    frame["mus_f1"] = [
        f1(ast.literal_eval(expected), ast.literal_eval(predicted))
        for expected, predicted in zip(frame["expected_mus"], frame["predicted_mus"])
    ]
    grouped = frame.groupby(
        ["model", "strategy", "mus_size", "total_rules"], as_index=False
    )["mus_f1"].mean()
    x_values = [7, 8, 10, 12, 15, 20, 25, 30]
    y_values = [2, 3, 4, 5, 7, 10, 15]
    fig, axes = plt.subplots(
        2, 3, figsize=(15, 9), sharex=True, sharey=True, constrained_layout=True
    )
    image = None
    for row, strategy in enumerate(["direct", "z3"]):
        for col, model in enumerate(MODEL_ORDER):
            ax = axes[row, col]
            sub = grouped[(grouped.model == model) & (grouped.strategy == strategy)]
            ax.set_title(f"{model}\n{STRATEGY_LABELS[strategy]}")
            pivot = sub.pivot_table(
                index="mus_size", columns="total_rules", values="mus_f1", aggfunc="mean"
            )
            if pivot.empty:
                ax.set_visible(False)
                continue
            pivot = pivot.reindex(index=y_values, columns=x_values)
            image = ax.imshow(pivot, vmin=0, vmax=1, cmap="RdYlGn", aspect="auto")
            ax.set_xticks(range(len(x_values)), [str(x) for x in x_values])
            ax.set_yticks(range(len(y_values)), [str(x) for x in y_values])
            for row_index in range(len(y_values)):
                for col_index in range(len(x_values)):
                    value = pivot.iloc[row_index, col_index]
                    if pd.notna(value):
                        ax.text(
                            col_index,
                            row_index,
                            f"{value:.2f}",
                            ha="center",
                            va="center",
                            fontsize=8,
                        )
    axes[0, 0].set_ylabel("Размер конфликта K")
    axes[1, 0].set_ylabel("Размер конфликта K")
    for ax in axes[1, :]:
        ax.set_xlabel("Общее число требований N")
    if image is None:
        raise RuntimeError("No heatmap data available")
    fig.colorbar(
        image, ax=axes.ravel().tolist(), label="Средняя F1-мера MUS", shrink=0.82
    )
    fig.suptitle("Зависимость качества от K и N (пустые ячейки: нет прогона)")
    fig.savefig(out / "fig_heatmap_k_n_mus_f1.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root", type=Path, help="Experiment directory with summary.csv/details.csv"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    _, details = load_data(args.root)
    plot_pattern_f1(details, args.output)
    plot_errors(details, args.output)
    plot_heatmap(details, args.output)
    details.to_csv(args.output / "article_figure_details.csv", index=False)
    print(f"Saved article figures to {args.output}")


if __name__ == "__main__":
    main()
