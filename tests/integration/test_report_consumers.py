"""Consumers must distinguish completed, historical and partial results."""

import json
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

from scripts import analyze_experiments, compare_runs, run_full_grid


def payload(
    status: str | None = "completed",
    *,
    version: str | None = "2",
    count: int = 0,
) -> dict[str, object]:
    data: dict[str, object] = {
        "metrics": {
            "planned": count,
            "processed": count,
            "total_evaluated": count,
            "infra_error_count": 0,
            "sat_accuracy": None,
            "mus_f1": None,
        },
        "details": [
            {
                "case_id": f"c{i}",
                "mus_size": 2,
                "expected_sat": True,
                "predicted_sat": None,
                "is_sat_correct": False,
                "expected_mus": [],
                "predicted_mus": [],
                "is_mus_correct": False,
                "metadata": {},
                "reasoning": "",
            }
            for i in range(count)
        ],
    }
    if status is not None:
        data["status"] = status
    if version is not None:
        data["report_schema_version"] = 2
        data["metric_definitions_version"] = version
    return data


@pytest.mark.parametrize(
    "cached_status,expected_runs,new_status",
    [
        ("running", 1, "completed"),
        ("completed", 0, "completed"),
        ("running", 1, "running"),
    ],
)
def test_full_grid_reuses_only_completed_reports(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cached_status: str,
    expected_runs: int,
    new_status: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_full_grid.py", "--pairs", "1"])
    cfg = run_full_grid.GridConfig("test", "tiny", 2, 5, 1, 42)
    monkeypatch.setattr(run_full_grid, "build_grid", lambda _pairs: [cfg])
    monkeypatch.setattr(
        run_full_grid,
        "MODELS",
        [{"label": "Offline", "load_key": "offline", "model_name": "offline"}],
    )
    monkeypatch.setattr(run_full_grid, "STRATEGIES", ["direct"])
    monkeypatch.setattr(run_full_grid, "unload_all", lambda *_args: None)
    monkeypatch.setattr(run_full_grid, "show_loaded_models", lambda *_args: "")
    monkeypatch.setattr(run_full_grid, "load_model", lambda **_kwargs: 0.0)

    def generate(_config: run_full_grid.GridConfig, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "offline_direct.json").write_text(
            json.dumps(payload(cached_status, count=2))
        )
        dataset = directory / "dataset_v2.jsonl"
        dataset.write_text("{}\n{}\n")
        return dataset

    runs: list[str] = []

    def evaluate(*, dataset_dir: str, output_file: str, **_kwargs: object) -> None:
        runs.append(dataset_dir)
        (Path(dataset_dir) / output_file).write_text(
            json.dumps(payload(new_status, count=2))
        )

    monkeypatch.setattr(run_full_grid, "generate_dataset", generate)
    monkeypatch.setattr(run_full_grid, "run_evaluation", evaluate)
    run_full_grid.main()
    assert len(runs) == expected_runs
    manifest = json.loads(
        next(tmp_path.glob("experiments/*/manifest.json")).read_text()
    )
    reports = [item for item in manifest if item["type"] == "report"]
    if new_status == "running":
        assert [item["status"] for item in reports] == ["error"]


def write_manifest(tmp_path: Path, reports: list[dict[str, object]]) -> None:
    manifest = []
    for index, report in enumerate(reports):
        path = tmp_path / f"report{index}.json"
        path.write_text(json.dumps(report), encoding="utf-8")
        manifest.append(
            {
                "type": "report",
                "planned": 0,
                "report": str(path),
                "model": "offline",
                "strategy": "direct",
                "config": {
                    "name": f"mus2_total{index + 3}",
                    "exp": "exp1_total_rules",
                    "mus_size": 2,
                    "total_rules": index + 3,
                },
            }
        )
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_analysis_filters_partial_reports_and_preserves_versions_and_null(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    write_manifest(
        tmp_path, [payload("running"), payload(), payload(None, version=None)]
    )
    monkeypatch.setattr(sys, "argv", ["analyze_experiments.py", str(tmp_path)])
    analyze_experiments.main()
    rows = pd.read_csv(
        tmp_path / "summary.csv", dtype={"metric_definitions_version": "string"}
    )
    assert len(rows) == 2
    assert rows.iloc[0]["metric_definitions_version"] == "2"
    assert pd.isna(rows.iloc[0]["mus_f1"])
    assert pd.isna(rows.iloc[1]["metric_definitions_version"])
    assert pd.isna(rows.iloc[1]["infrastructure_error_rate"])
    assert (tmp_path / "plots/metrics_2").is_dir()
    assert (tmp_path / "plots/metrics_legacy").is_dir()


def test_combining_versions_does_not_deduplicate_or_pool_their_metrics(
    tmp_path: Path,
) -> None:
    paths = [tmp_path / name for name in ("old", "new")]
    for directory, version in zip(paths, [None, "3"], strict=True):
        directory.mkdir()
        pd.DataFrame(
            [
                {
                    "config": "mus2_total3",
                    "model": "offline",
                    "strategy": "direct",
                    "mus_f1": None,
                    "sat_accuracy": 0.5,
                    "metric_definitions_version": version,
                    "report_schema_version": 3 if version else None,
                }
            ]
        ).to_csv(directory / "summary.csv", index=False)
    merged = compare_runs.load_summaries(paths)
    assert len(merged) == 2
    assert merged["metric_definitions_version"].tolist() == ["legacy", "3"]
    assert merged["mus_f1"].isna().all()


def test_empty_analysis_does_not_crash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_manifest(tmp_path, [payload("running")])
    monkeypatch.setattr(sys, "argv", ["analyze_experiments.py", str(tmp_path)])
    analyze_experiments.main()
    assert (tmp_path / "summary.csv").exists()


def test_analysis_plots_null_metrics_without_turning_them_into_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    write_manifest(tmp_path, [payload()])
    monkeypatch.setattr(sys, "argv", ["analyze_experiments.py", str(tmp_path)])
    analyze_experiments.main()
    summary = pd.read_csv(tmp_path / "summary.csv")
    assert summary["mus_f1"].isna().all()
    assert list((tmp_path / "plots").glob("*.png"))


@pytest.mark.parametrize(
    "cached_status,expected_runs", [("running", 1), ("completed", 0), (None, 0)]
)
def test_smoke_grid_completion_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    cached_status: str | None,
    expected_runs: int,
) -> None:
    # This CLI registers signal handlers on import: defer until fixture setup.
    from scripts import run_smoke_grid  # pylint: disable=import-outside-toplevel

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        run_smoke_grid,
        "GRID",
        [{"exp": "test", "name": "tiny", "mus_size": 2, "total_rules": 3}],
    )
    monkeypatch.setattr(run_smoke_grid, "MODELS", ["offline"])
    monkeypatch.setattr(run_smoke_grid, "STRATEGIES", ["direct"])
    monkeypatch.setattr(time, "strftime", lambda *_args: "review")
    directory = tmp_path / "experiments/review_quick_grid/tiny/dataset"
    directory.mkdir(parents=True)
    (directory / "dataset_v2.jsonl").write_text("{}\n{}\n")
    report_path = directory / "offline_direct.json"
    report_path.write_text(
        json.dumps(
            payload(
                cached_status, version=None if cached_status is None else "2", count=2
            )
        )
    )
    runs: list[str] = []

    def evaluate(**_kwargs: object) -> None:
        runs.append("run")
        report_path.write_text(json.dumps(payload(count=2)))

    monkeypatch.setattr(run_smoke_grid, "run_evaluation", evaluate)
    run_smoke_grid.main()
    assert len(runs) == expected_runs
