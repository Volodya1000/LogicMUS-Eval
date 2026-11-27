"""A–L: tiny durable fixtures; all inference is mocked, analysis is offline."""
# Imports stay inside tests for missing-feature regressions and offline boundaries.
# pylint: disable=import-outside-toplevel,redefined-outer-name

import csv
import hashlib
import json
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace

import pytest
from test_controlled_runner import answer, config_for, fixture_series

from logicmus_eval.runner.execution import new_run

series = fixture_series


@pytest.fixture(name="saved")
def fixture_saved(series, tmp_path):
    root = tmp_path / "run"
    new_run(config_for(series), root, completion=lambda **_: answer(usage=False))
    return root


def plan_for(root, **updates):
    run_id = json.loads((root / "run.manifest.json").read_text())["payload"]["run_id"]
    return {
        "analysis_version": "controlled-analysis-v1",
        "purpose": "development",
        "groups": [{"name": "dev", "run_ids": [run_id]}],
        "intervals": {"seed": 42, "repeats": 100},
        **updates,
    }


def analyze(roots, plan, output):
    from logicmus_eval.analysis import analyze as run_analysis
    from logicmus_eval.analysis.plan import AnalysisPlan

    return run_analysis(roots, AnalysisPlan.model_validate(plan), output)


def read_csv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def hashes(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


def test_repeated_root_subgroup_source_hash_and_null(saved, tmp_path):
    before = hashes(saved)
    sub = next((saved / "reports").glob("*.json"))
    output = tmp_path / "analysis"
    analyze([saved, saved, sub], plan_for(saved), output)
    assert hashes(saved) == before
    cases = read_csv(output / "cases.csv")
    summary = read_csv(output / "summary.csv")
    assert len(cases) == 8
    assert {r["pattern_id"] for r in cases} == {"fork"}
    assert {r["planned"] for r in summary} == {"4"}
    assert {r["families"] for r in summary} == {"2"}
    assert {r["total_tokens_consumed"] for r in summary} == {""}
    assert len({r["family_id"] for r in cases}) == 2
    assert len({r["N"] for r in cases}) == 2
    manifest = json.loads((output / "analysis.manifest.json").read_text())
    assert manifest["plan_sha256"]
    assert manifest["inputs"][0]["journal_head_sha256"]


def test_analysis_historical_identity_without_resume(saved, tmp_path):
    # The historical source hash must be verified internally, not against checkout.
    output = tmp_path / "analysis"
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps(plan_for(saved)))
    child = """
import importlib.abc, sys
class Offline(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname in {'litellm', 'logicmus_eval.extractor', 'logicmus_eval.runner.inference', 'logicmus_eval.runner.execution', 'logicmus_eval.runner.transport'}:
            raise AssertionError('Network/execution import: ' + fullname)
sys.meta_path.insert(0, Offline())
from logicmus_eval.hashing import compute_source_bundle_hash
from typer.testing import CliRunner
from logicmus_eval.cli import app
r = CliRunner().invoke(app, ['analyze-controlled', '--run', sys.argv[1], '--plan', sys.argv[2], '--output', sys.argv[3], '--no-plots'])
assert r.exit_code == 0, r.output + str(r.exception)
"""
    result = subprocess.run(
        [sys.executable, "-c", child, str(saved), str(plan), str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_changed_report_and_confirmation_contamination_rejected(saved, tmp_path):
    with pytest.raises(ValueError, match="purpose"):
        analyze(
            [saved], plan_for(saved, purpose="confirmation"), tmp_path / "bad-purpose"
        )
    data = json.loads((saved / "report.json").read_text(encoding="utf-8"))
    data["details"][0]["is_sat_correct"] = not data["details"][0]["is_sat_correct"]
    (saved / "report.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="outcomes|metrics"):
        analyze([saved], plan_for(saved), tmp_path / "bad-report")


def test_incomplete_only_diagnostic(series, tmp_path):
    root = tmp_path / "partial"

    def interrupt(**_):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        new_run(config_for(series), root, completion=interrupt)
    with pytest.raises(ValueError, match="complete"):
        analyze([root], plan_for(root), tmp_path / "bad")
    output = tmp_path / "diagnostic"
    analyze([root], plan_for(root, mode="diagnostic"), output)
    assert not read_csv(output / "summary.csv")
    diagnostics = json.loads((output / "diagnostics.json").read_text())
    assert diagnostics["runs"][0]["processed"] == 0
    assert diagnostics["runs"][0]["planned"] == 8


def test_missing_pair_rejected_with_ids(saved, tmp_path):
    plan = plan_for(
        saved,
        contrasts=[
            {
                "name": "direct-z3",
                "kind": "strategy",
                "metric": "mus_exact_match",
                "left": {"group": "dev", "strategy": "direct", "N": 4},
                "right": {"group": "dev", "strategy": "z3", "N": 4},
            }
        ],
    )
    output = tmp_path / "missing"
    with pytest.raises(ValueError, match="missing"):
        analyze([saved], plan, output)
    diagnostics = json.loads((output / "diagnostics.json").read_text())
    assert diagnostics["contrasts"][0]["missing_right"]


def test_noise_pair_preserves_families(saved, tmp_path):
    plan = plan_for(
        saved,
        contrasts=[
            {
                "name": "noise",
                "kind": "noise",
                "metric": "mus_f1",
                "left": {"group": "dev", "strategy": "direct", "N": 4},
                "right": {"group": "dev", "strategy": "direct", "N": 7},
            }
        ],
    )
    output = tmp_path / "paired"
    analyze([saved], plan, output)
    row = read_csv(output / "contrasts.csv")[0]
    assert row["families"] == "2"
    assert row["estimate"] == "0.0"
    assert row["degenerate"] == "True"


def test_legacy_consumers_refuse_controlled(saved):
    from scripts import analyze_patterns, compare_runs, make_article_figures

    for call in [
        lambda: analyze_patterns.load_data(saved),
        lambda: make_article_figures.load_data(saved),
        lambda: compare_runs.load_summaries([saved]),
    ]:
        with pytest.raises(ValueError, match="analyze-controlled"):
            call()


@pytest.mark.parametrize(
    "field",
    [
        "runner_protocol",
        "transport_protocol",
        "source_bundle_sha256",
        "runtime",
        "metric_definitions_version",
        "z3_execution_protocol_version",
        "generation",
        "schema",
        "prompt",
        "timeout",
    ],
)
def test_compatibility_checks_saved_conditions_beyond_metric_version(saved, field):
    from logicmus_eval.analysis import _rows
    from logicmus_eval.analysis.sources import check_compatibility, load_snapshots

    original = load_snapshots([saved])[0]
    changed = replace(
        original,
        payload=deepcopy(original.payload),
        requests=deepcopy(original.requests),
    )
    identity = changed.payload["identity"]
    if field == "generation":
        identity["config"]["models"][0]["generation"]["temperature"] = 0.8
    elif field == "timeout":
        identity["config"]["request_timeout_seconds"] = 200.0
    elif field in {"schema", "prompt"}:
        for request in changed.requests.values():
            if field == "schema":
                request["body"]["response_format"]["json_schema"]["name"] = "changed"
            else:
                request["body"]["messages"][0]["content"] += " changed"
    else:
        identity[field] = "changed"
    first, second = _rows(original), _rows(changed)
    if field == "z3_execution_protocol_version":
        # Z3 conditions are scoped; direct legitimately has no Z3 execution.
        check_compatibility(first + second)
        for row in first + second:
            row["strategy"] = "z3"
    with pytest.raises(ValueError, match="Incompatible|Unsupported"):
        check_compatibility(first + second)


def test_planned_direct_z3_allows_different_prompts_and_schemas(series, tmp_path):
    config = config_for(series)
    config.strategies = ["direct", "z3"]
    root = tmp_path / "both"
    new_run(config, root, completion=lambda **_: answer())
    plan = plan_for(
        root,
        contrasts=[
            {
                "name": "direct-z3",
                "kind": "strategy",
                "left": {"group": "dev", "strategy": "direct", "N": 4},
                "right": {"group": "dev", "strategy": "z3", "N": 4},
            }
        ],
    )
    output = tmp_path / "paired"
    analyze([root], plan, output)
    assert len(read_csv(output / "cases.csv")) == 16
    assert read_csv(output / "contrasts.csv")[0]["pairs"] == "2"


def test_distinct_runs_not_silently_deduplicated_and_diagnostic_excluded(
    saved, series, tmp_path
):
    config = config_for(series)
    other = tmp_path / "similar-run"
    new_run(config, other, completion=lambda **_: answer())
    plan = plan_for(saved)
    other_id = plan_for(other)["groups"][0]["run_ids"][0]
    plan["groups"][0]["run_ids"].append(other_id)
    with pytest.raises(ValueError, match="Conflicting repeated"):
        analyze([saved, other], plan, tmp_path / "conflict")
    plan["groups"] = [
        {"name": "first", "run_ids": plan_for(saved)["groups"][0]["run_ids"]},
        {"name": "second", "run_ids": [other_id]},
    ]
    output = tmp_path / "separate"
    analyze([saved, other], plan, output)
    assert len(read_csv(output / "cases.csv")) == 16
    config.diagnostic_parent_run = plan_for(saved)["groups"][0]["run_ids"][0]
    diagnostic = tmp_path / "rerun"
    new_run(config, diagnostic, completion=lambda **_: answer())
    with pytest.raises(ValueError, match="Diagnostic rerun"):
        analyze([diagnostic], plan_for(diagnostic), tmp_path / "no-diagnostic")


def test_corrupt_manifest_journal_and_stale_subgroup_rejected(saved, tmp_path):
    import shutil
    import sqlite3

    for kind in ["manifest", "journal", "stale"]:
        root = tmp_path / kind
        shutil.copytree(saved, root)
        if kind == "manifest":
            path = root / "run.manifest.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            data["payload"]["created_at"] = "changed"
            path.write_text(json.dumps(data), encoding="utf-8")
        elif kind == "journal":
            with sqlite3.connect(root / "journal.sqlite3") as db:
                db.execute(
                    "DELETE FROM events WHERE seq = (SELECT MAX(seq) FROM events)"
                )
        else:
            path = next((root / "reports").glob("*.json"))
            data = json.loads(path.read_text(encoding="utf-8"))
            data["runner_provenance"]["journal_event_count"] = 0
            path.write_text(json.dumps(data), encoding="utf-8")
        inputs = (
            [root, next((root / "reports").glob("*.json"))]
            if kind == "stale"
            else [root]
        )
        with pytest.raises(ValueError, match="provenance|journal"):
            analyze(inputs, plan_for(saved), tmp_path / f"reject-{kind}")


def test_legacy_reading_is_explicit_descriptive_and_does_not_invent_identity(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(
        json.dumps({"metrics": {"mus_f1": 0.5}, "details": [{"case_id": "local-0"}]})
    )
    plan = {
        "analysis_version": "controlled-analysis-v1",
        "purpose": "development",
        "mode": "legacy",
        "groups": [{"name": "legacy", "run_ids": ["unattested"]}],
        "intervals": {"seed": 1},
    }
    output = tmp_path / "legacy"
    analyze([path], plan, output)
    row = read_csv(output / "legacy.csv")[0]
    assert row["provenance_status"] == "legacy"
    assert "family_id" not in row
    assert not (output / "contrasts.csv").exists()


@pytest.mark.parametrize(
    "field",
    [
        "metric_definitions_version",
        "report_schema_version",
        "z3_execution_protocol_version",
    ],
)
def test_report_versions_must_match_saved_identity(saved, tmp_path, field):
    data = json.loads((saved / "report.json").read_text(encoding="utf-8"))
    data[field] = 999 if field == "report_schema_version" else "999"
    (saved / "report.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="version"):
        analyze([saved], plan_for(saved), tmp_path / "bad-version")


def test_demo_tables_and_all_figure_families(series, tmp_path, monkeypatch):  # pylint: disable=too-many-locals
    """Small artificial demonstration, never a model performance experiment."""
    from pathlib import Path

    from logicmus_eval import experiment_preparation
    from logicmus_eval.analysis.plotting import plot_tables
    from logicmus_eval.experiment_plan import ExperimentPlan
    from logicmus_eval.experiment_preparation import prepare_experiment
    from logicmus_eval.runner.preflight import preflight

    mock_probe = experiment_preparation.calculate_leakage
    assert series[1].ready_for_evaluation

    def multi_topology_probe(dataset, ks):
        raw = mock_probe(dataset, ks)
        # The tiny one-topology fixture shares one metric instance. Detach each
        # serialized field before assigning different fold counts per topology.
        report = type(raw).model_validate_json(raw.model_dump_json())
        counts = {
            "global": len({case.metadata["family_id"] for case in dataset}),
            **{
                f"mus_size={k}": len(
                    {
                        case.metadata["family_id"]
                        for case in dataset
                        if case.mus_size == k
                    }
                )
                for k in ks
            },
        }
        views = [
            {
                "global": {
                    "word_tfidf": report.global_word,
                    "char_tfidf": report.global_char,
                },
                **report.by_mus_size,
            },
            *report.by_input.values(),
        ]
        for view in views:
            for group, metrics in view.items():
                for metric in metrics.values():
                    metric.n_splits = min(5, counts[group])
                    metric.fold_balanced_accuracies = [0.5] * metric.n_splits
        return report

    monkeypatch.setattr(
        experiment_preparation, "calculate_leakage", multi_topology_probe
    )

    payload = json.loads(
        Path("configs/development-controlled-v1.json").read_text(encoding="utf-8")
    )
    payload["seeds"] = [42]
    root = tmp_path / "demo-series"
    manifest = prepare_experiment(ExperimentPlan.model_validate(payload), root)
    config = config_for((root, manifest))
    config.models[0].model_id = "offline/mock-demonstration"
    config.strategies = ["direct", "z3"]
    ready = preflight(config)
    jobs = {json.dumps(job.request["body"], sort_keys=True): job for job in ready.jobs}

    def mock_response(**request):
        job = jobs[json.dumps(request["body"], sort_keys=True)]
        case = job.case
        # Z3 gets an intentionally invalid schema and a finalized error. Direct
        # gets known exact/partial/wrong answers, including a controlled N change.
        partial = case.metadata["pair_index"] == 1 and not case.is_satisfiable
        wrong = partial and case.metadata["total_rules"] >= 10
        core = case.mus_expected[:-1] if partial else case.mus_expected
        return answer(
            json.dumps(
                {
                    "reasoning": "artificial fixture only",
                    "is_sat": True if wrong else case.is_satisfiable,
                    "conflict_core": [] if wrong else core,
                }
            )
        )

    saved = tmp_path / "demo-run"
    new_run(config, saved, completion=mock_response)
    plan = plan_for(
        saved,
        contrasts=[
            {
                "name": "mock-direct-vs-z3",
                "kind": "strategy",
                "metric": "mus_exact_match",
                "left": {
                    "group": "dev",
                    "series_id": "noise-chain",
                    "strategy": "direct",
                    "N": 6,
                },
                "right": {
                    "group": "dev",
                    "series_id": "noise-chain",
                    "strategy": "z3",
                    "N": 6,
                },
            },
            {
                "name": "mock-noise-difference",
                "kind": "noise",
                "metric": "mus_f1",
                "left": {
                    "group": "dev",
                    "series_id": "noise-chain",
                    "strategy": "direct",
                    "N": 6,
                },
                "right": {
                    "group": "dev",
                    "series_id": "noise-chain",
                    "strategy": "direct",
                    "N": 10,
                },
            },
        ],
    )
    output = tmp_path / "demo-analysis"
    analyze([saved], plan, output)
    plot_tables(output)
    assert len(list((output / "figures").glob("*.png"))) == 14
    assert len(read_csv(output / "cases.csv")) == 72
    paired = read_csv(output / "contrasts.csv")
    assert float(paired[1]["estimate"]) == pytest.approx(-0.4)
    assert float(paired[1]["low"]) == pytest.approx(-0.8)
    assert float(paired[1]["high"]) == 0
    assert len(read_csv(output / "summary.csv")) == 18
    # Plotting must reject edits to any table rather than silently redraw.
    with (output / "summary.csv").open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="changed"):
        plot_tables(output)
