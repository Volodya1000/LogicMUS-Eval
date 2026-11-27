"""A-L: tiny durable fixtures; all inference is mocked, analysis is offline."""

# pylint: disable=redefined-outer-name
import csv
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from test_controlled_runner import answer, config_for, fixture_series

from logicmus_eval import experiment_preparation
from logicmus_eval.analysis import analyze as run_analysis
from logicmus_eval.analysis import plotting
from logicmus_eval.analysis.contrasts import contrast_table
from logicmus_eval.analysis.models import ContrastDiagnostic
from logicmus_eval.analysis.plan import AnalysisPlan
from logicmus_eval.analysis.plotting import plot_tables
from logicmus_eval.analysis.selection import rows_for
from logicmus_eval.analysis.sources import check_compatibility, load_snapshots
from logicmus_eval.analysis.tables import metrics_for, observations, summary_table
from logicmus_eval.evaluation.metrics import semantics
from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.experiment_preparation import prepare_experiment
from logicmus_eval.runner import journal
from logicmus_eval.runner.execution import new_run
from logicmus_eval.runner.journal import RunJournal
from logicmus_eval.runner.preflight import digest, preflight
from logicmus_eval.runner.snapshot_models import SavedPayload, SavedRequest
from scripts import analyze_patterns, compare_runs, make_article_figures

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


def test_plot_failure_publishes_rejected_manifest_and_partial_artifacts(
    saved, tmp_path, monkeypatch
):

    def broken_plot(output, *, finalize):
        assert finalize is False
        manifest = json.loads(
            (output / "analysis.manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["status"] != "complete"
        (output / "figures").mkdir()
        (output / "figures" / "partial.png").write_bytes(b"partial drawing")
        raise RuntimeError("plot regression")

    monkeypatch.setattr(plotting, "plot_tables", broken_plot)
    output = tmp_path / "plot-failure"
    with pytest.raises(RuntimeError, match="plot regression"):
        run_analysis(
            [saved], AnalysisPlan.model_validate(plan_for(saved)), output, plots=True
        )
    manifest = json.loads(
        (output / "analysis.manifest.json").read_text(encoding="utf-8")
    )
    diagnostic = json.loads((output / "diagnostics.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "rejected"
    assert "plot regression" in diagnostic["error"]
    assert {
        "diagnostics.json",
        "cases.csv",
        "summary.csv",
        "contrasts.csv",
        "figures/partial.png",
    } <= manifest["artifacts"].keys()
    for name, checksum in manifest["artifacts"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == checksum


def test_snapshot_report_reads_are_inside_the_runner_lock(saved, monkeypatch):
    manifest = json.loads((saved / "run.manifest.json").read_text(encoding="utf-8"))
    old_text, old_bytes = Path.read_text, Path.read_bytes
    seen = []

    def check(path):
        if path.resolve() == (saved / "report.json").resolve():
            with (
                pytest.raises(ValueError, match="Another writer"),
                RunJournal(saved.resolve(), manifest["manifest_sha256"]),
            ):
                pass
            seen.append(path)

    def read_text(path, *args, **kwargs):
        check(path)
        return old_text(path, *args, **kwargs)

    def read_bytes(path):
        check(path)
        return old_bytes(path)

    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    snapshots = load_snapshots([saved, next((saved / "reports").glob("*.json"))])
    assert len(snapshots) == 1
    assert seen


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
    original = load_snapshots([saved])[0]
    payload = original.payload.saved_json()
    requests = {key: request.saved_json() for key, request in original.requests.items()}
    identity = payload["identity"]
    if field == "generation":
        identity["config"]["models"][0]["generation"]["temperature"] = 0.8
    elif field == "timeout":
        identity["config"]["request_timeout_seconds"] = 200.0
    elif field in {"schema", "prompt"}:
        for request in requests.values():
            if field == "schema":
                request["body"]["response_format"]["json_schema"]["name"] = "changed"
            else:
                request["body"]["messages"][0]["content"] += " changed"
    elif field == "runtime":
        identity[field]["python"] = "changed"
    else:
        identity[field] = "changed"
    changed = replace(
        original,
        payload=SavedPayload.model_validate(payload),
        requests={
            key: SavedRequest.model_validate(request)
            for key, request in requests.items()
        },
    )
    first, second = rows_for(original), rows_for(changed)
    if field == "z3_execution_protocol_version":
        check_compatibility(first + second)
        first = [
            replace(row, dimensions=replace(row.dimensions, strategy="z3"))
            for row in first
        ]
        second = [
            replace(row, dimensions=replace(row.dimensions, strategy="z3"))
            for row in second
        ]
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


def test_same_local_id_cells_patterns_and_repeated_family_are_separate(saved):
    snapshot = load_snapshots([saved])[0]
    rows = []
    for pattern in ["fork", "merge"]:
        for row in rows_for(snapshot, "dev"):
            rows.append(
                replace(
                    row,
                    dimensions=replace(row.dimensions, pattern_id=pattern),
                    outcome=row.outcome.model_copy(update={"case_id": "same-local-id"}),
                )
            )
    plan = AnalysisPlan.model_validate(plan_for(saved))
    summary = summary_table(rows, plan)
    assert len(summary) == 4
    assert {(r.dimensions.pattern_id, r.dimensions.n) for r in summary} == {
        ("fork", 4),
        ("fork", 7),
        ("merge", 4),
        ("merge", 7),
    }
    assert all(r.families == 2 for r in summary)
    assert summary == summary_table(list(reversed(rows)), plan)
    duplicated = summary_table(rows + rows, plan)
    assert all(
        r.intervals["mus_exact_match"]["status"] == "unavailable" for r in duplicated
    )
    assert all(r.intervals["mus_f1"]["families"] == 2 for r in duplicated)


def test_final_hashes_cover_diagnostics_figures_and_plan(saved, tmp_path):
    output = tmp_path / "all-artifacts"
    run_analysis(
        [saved], AnalysisPlan.model_validate(plan_for(saved)), output, plots=True
    )
    manifest = json.loads(
        (output / "analysis.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "complete"
    assert manifest["plots_requested"] is True
    assert digest(manifest["plan"]) == manifest["plan_sha256"]
    retained = {
        p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()
    }
    assert retained - {"analysis.manifest.json"} == manifest["artifacts"].keys()
    for name, checksum in manifest["artifacts"].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == checksum
    (output / "figures" / "paired_differences.png").write_bytes(b"modified")
    with pytest.raises(ValueError, match="artifact changed"):
        plot_tables(output)


def test_plot_reader_accepts_unavailable_interval_next_to_available(saved, tmp_path):
    output = tmp_path / "mixed-intervals"
    analyze([saved], plan_for(saved), output)
    rows = read_csv(output / "summary.csv")
    rows[1].update(
        {
            "mus_f1_ci_status": "unavailable",
            "mus_f1_ci_reason": "insufficient independent families",
            "mus_f1_ci_low": "",
            "mus_f1_ci_high": "",
            "mus_f1_ci_degenerate": "",
            "mus_f1_ci_method": "",
            "mus_f1_ci_families": "1",
        }
    )
    with (output / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    manifest_path = output / "analysis.manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["summary.csv"] = hashlib.sha256(
        (output / "summary.csv").read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    plot_tables(output)
    published = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert published["status"] == "complete"
    assert (output / "figures" / "noise_sweep_mus_f1.png").is_file()


def test_shared_metric_semantics_reach_estimates_intervals_and_contrasts(
    saved, monkeypatch
):

    snapshot = load_snapshots([saved])[0]
    rows = rows_for(snapshot, "dev")
    original = semantics.observation

    def contribution(report, metric):
        if metric == "mus_f1":
            return None if report.expected_sat else 0.25
        return original(report, metric)

    monkeypatch.setattr(semantics, "observation", contribution)
    plan = AnalysisPlan.model_validate(
        plan_for(
            saved,
            contrasts=[
                {
                    "name": "noise",
                    "kind": "noise",
                    "metric": "mus_f1",
                    "left": {"group": "dev", "N": 4},
                    "right": {"group": "dev", "N": 7},
                }
            ],
        )
    )
    assert metrics_for([r.outcome for r in rows], len(rows))["mus_f1"] == 0.25
    assert len(observations(rows, "mus_f1")) == 4
    assert {item.value for item in observations(rows, "mus_f1")} == {0.25}
    for summary in summary_table(rows, plan):
        assert summary.metrics["mus_f1"] == 0.25
        assert (
            summary.intervals["mus_f1"]["low"]
            == summary.intervals["mus_f1"]["high"]
            == 0.25
        )
    diagnostic: list[ContrastDiagnostic] = []
    contrast = contrast_table(rows, plan, diagnostic)[0]
    assert contrast.estimate == 0
    assert contrast.interval["low"] == contrast.interval["high"] == 0


def test_snapshot_hashes_are_of_the_exact_parsed_report_bytes(saved, monkeypatch):
    raw = (saved / "report.json").read_bytes()
    original = Path.read_bytes
    reads = []

    def read_bytes(path):
        if path.resolve() == (saved / "report.json").resolve():
            reads.append(path)
            if len(reads) > 1:
                return b"not the report that was validated"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    snapshot = load_snapshots([saved])[0]
    assert len(reads) == 1
    assert snapshot.evidence.files["report.json"] == hashlib.sha256(raw).hexdigest()


def test_publication_records_keyboard_interrupt_and_no_complete_status(
    saved, tmp_path, monkeypatch
):

    def interrupted(_output, *, finalize):
        assert finalize is False
        raise KeyboardInterrupt

    monkeypatch.setattr(plotting, "plot_tables", interrupted)
    output = tmp_path / "interrupted-analysis"
    with pytest.raises(KeyboardInterrupt):
        run_analysis(
            [saved], AnalysisPlan.model_validate(plan_for(saved)), output, plots=True
        )
    manifest = json.loads(
        (output / "analysis.manifest.json").read_text(encoding="utf-8")
    )
    diagnostic = json.loads((output / "diagnostics.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "rejected"
    assert diagnostic["error"] == "KeyboardInterrupt"


@pytest.mark.parametrize("status", ["running", "complete"])
def test_uncommitted_running_tables_cannot_be_promoted_by_standalone_plotting(
    saved, tmp_path, monkeypatch, status
):

    output = tmp_path / "uncommitted"
    analyze([saved], plan_for(saved), output)
    path = output / "analysis.manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["status"] = status
    manifest["plots_requested"] = True
    manifest["artifacts"] = {
        "diagnostics.json": manifest["artifacts"]["diagnostics.json"]
    }
    path.write_text(json.dumps(manifest), encoding="utf-8")

    def forbidden_render(*_):
        raise AssertionError("uncommitted tables reached rendering")

    monkeypatch.setattr(plotting, "_render", forbidden_render)
    with pytest.raises(ValueError, match="completed|hash"):
        plotting.plot_tables(output)


def test_rejected_contrast_keeps_verified_cases_and_summary(saved, tmp_path):
    plan = plan_for(
        saved,
        contrasts=[
            {
                "name": "missing",
                "kind": "strategy",
                "left": {"group": "dev", "N": 4, "strategy": "direct"},
                "right": {"group": "dev", "N": 4, "strategy": "z3"},
            }
        ],
    )
    output = tmp_path / "partial-tables"
    with pytest.raises(ValueError, match="missing"):
        analyze([saved], plan, output)
    assert len(read_csv(output / "cases.csv")) == 8
    assert len(read_csv(output / "summary.csv")) == 2
    manifest = json.loads(
        (output / "analysis.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["status"] == "rejected"
    assert {"cases.csv", "summary.csv", "diagnostics.json"} <= manifest[
        "artifacts"
    ].keys()


def test_failed_atomic_complete_publication_retains_valid_manifest_and_error(
    saved, tmp_path, monkeypatch
):

    original_replace = journal.os.replace

    def failed_complete(source, destination):
        if Path(destination).name == "analysis.manifest.json":
            payload = json.loads(Path(source).read_text(encoding="utf-8"))
            if payload["status"] == "complete":
                raise OSError("manifest publication regression")
        return original_replace(source, destination)

    monkeypatch.setattr(journal.os, "replace", failed_complete)
    output = tmp_path / "atomic-failure"
    with pytest.raises(OSError, match="publication regression"):
        analyze([saved], plan_for(saved), output)
    manifest = json.loads(
        (output / "analysis.manifest.json").read_text(encoding="utf-8")
    )
    diagnostic = json.loads((output / "diagnostics.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "rejected"
    assert "manifest publication regression" in diagnostic["error"]
    assert not list(output.glob("analysis.manifest.json.*"))
