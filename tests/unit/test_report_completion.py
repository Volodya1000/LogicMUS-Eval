"""Completion policy is conservative for versioned reports and explicit for legacy."""

import json
from pathlib import Path

import pytest

from logicmus_eval.evaluation.reports import (
    report_is_complete,
    require_completed_report,
)


@pytest.mark.parametrize(
    "extra,complete",
    [
        ({}, False),
        (
            {
                "status": "running",
                "report_schema_version": 3,
                "metric_definitions_version": "3",
            },
            False,
        ),
        (
            {
                "status": "completed",
                "report_schema_version": 3,
                "metric_definitions_version": "3",
            },
            True,
        ),
        (
            {
                "status": "completed",
                "report_schema_version": 2,
                "metric_definitions_version": "2",
            },
            True,
        ),
        (
            {
                "status": "completed",
                "report_schema_version": 99,
                "metric_definitions_version": "99",
            },
            False,
        ),
        ({"report_schema_version": 3, "metric_definitions_version": "3"}, False),
        (
            {
                "status": "completed",
                "report_schema_version": 3,
                "metric_definitions_version": "3",
                "metrics": {"planned": 2, "processed": 0},
            },
            False,
        ),
        (
            {
                "status": "completed",
                "report_schema_version": 3,
                "metric_definitions_version": "3",
                "metrics": {"planned": True, "processed": False},
            },
            False,
        ),
    ],
)
def test_completion_status_and_counter_invariants(
    tmp_path: Path, extra: dict[str, object], complete: bool
) -> None:
    path = tmp_path / "report.json"
    path.write_text(
        json.dumps({"metrics": {"planned": 0, "processed": 0}, "details": [], **extra})
    )
    assert report_is_complete(path) is complete


def test_legacy_metrics_and_metadata_are_not_upgraded(tmp_path: Path) -> None:
    path = tmp_path / "old.json"
    path.write_text(
        json.dumps(
            {
                "metrics": {"sat_accuracy": 0.9, "infrastructure_error_rate": 0.2},
                "details": [],
            }
        )
    )
    report = require_completed_report(path, expected_cases=0)
    assert report.metric_definitions_version is None
    assert report.metrics["infrastructure_error_rate"] == 0.2
    assert "execution_error_rate" not in report.metrics


def test_legacy_unfinished_run_info_and_broken_files_are_not_complete(
    tmp_path: Path,
) -> None:
    path = tmp_path / "old.json"
    path.write_text(
        json.dumps(
            {
                "metrics": {},
                "details": [],
                "run_info": {
                    "model_name": "offline",
                    "strategy": "direct",
                    "dataset_filename": "old.jsonl",
                    "dataset_sha256": "abc",
                    "prompt_template_hash": "def",
                    "started_at": "2024-01-01T00:00:00Z",
                    "finished_at": None,
                    "total_cases_processed": 0,
                },
            }
        )
    )
    assert not report_is_complete(path)
    path.write_text("broken")
    assert not report_is_complete(path)
    assert not report_is_complete(tmp_path / "missing.json")


def test_legacy_partial_needs_dataset_count_and_limit_context(tmp_path: Path) -> None:
    detail = {
        "case_id": "one",
        "mus_size": 1,
        "expected_sat": False,
        "predicted_sat": None,
        "is_sat_correct": False,
        "expected_mus": ["R1"],
        "predicted_mus": [],
        "is_mus_correct": False,
        "metadata": {},
        "reasoning": "analysis",
    }
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"metrics": {}, "details": [detail]}))
    (tmp_path / "dataset_v1_frozen.jsonl").write_text("{}\n{}\n")
    assert not report_is_complete(path)
    # A deliberately limited, completed old run remains usable.
    assert report_is_complete(path, limit=1)
    path.write_text(
        json.dumps({"metrics": {}, "details": [detail, {**detail, "case_id": "two"}]})
    )
    assert report_is_complete(path)
