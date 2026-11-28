"""Parent admission remains mandatory for a small infrastructure-only queue."""

# Registered fixtures install the mock audit and retain pytest's fixture names.
# pylint: disable=redefined-outer-name,unused-argument,import-outside-toplevel

import json
import subprocess
import sys

import pytest
from test_controlled_runner import answer, config_for, fixture_series

from logicmus_eval.analysis import analyze
from logicmus_eval.analysis.plan import AnalysisPlan
from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.experiment_preparation import prepare_experiment
from logicmus_eval.runner.config import RunConfig
from logicmus_eval.runner.execution import new_run, resume_run
from logicmus_eval.runner.preflight import preflight
from logicmus_eval.runner.snapshot import read_snapshot

series = fixture_series


@pytest.fixture(name="smoke")
def fixture_smoke(series, tmp_path, monkeypatch):
    # The existing mock fixture installs a measured-probe stand-in. It is used
    # only for admission plumbing, never reported as measured scientific data.
    from logicmus_eval import experiment_preparation
    from logicmus_eval.infrastructure_smoke import SelectionRule, prepare_selection

    mock_probe = experiment_preparation.calculate_leakage

    def counted_mock_probe(dataset, ks):
        report = mock_probe(dataset, ks)
        folds = min(5, len({case.metadata["family_id"] for case in dataset}))
        # This fixture's K is always 4, so global/per-K group counts coincide.
        for metric in (
            report.global_word,
            report.global_char,
            *(
                metric
                for view in report.by_input.values()  # pylint: disable=no-member
                for group in view.values()
                for metric in group.values()
            ),
            *(
                metric
                for group in report.by_mus_size.values()  # pylint: disable=no-member
                for metric in group.values()
            ),
        ):
            metric.n_splits = folds
            metric.fold_balanced_accuracies = [0.5] * folds
        return report

    monkeypatch.setattr(experiment_preparation, "calculate_leakage", counted_mock_probe)

    plan = ExperimentPlan.model_validate(
        {
            "protocol_version": "controlled-v1",
            "purpose": "development",
            "seeds": [42, 44],
            "pairs_per_seed": 1,
            "series": [
                {
                    "series_id": pattern,
                    "kind": "noise_sweep",
                    "patterns": [{"pattern_id": pattern, "k_values": [4]}],
                    "n_values": [8, 12],
                }
                for pattern in ("chain", "math")
            ],
        }
    )
    root = tmp_path / "parent"
    manifest = prepare_experiment(plan, root)
    assert manifest.ready_for_evaluation
    parent = root / "series.manifest.json"
    receipt_path = tmp_path / "selection.json"
    receipt = prepare_selection(
        parent,
        SelectionRule(
            selection_version="infrastructure-smoke-v1", seed=42, pair_index=0
        ),
        receipt_path,
    )
    payload = config_for((root, manifest)).model_dump(mode="json")
    payload["strategies"] = ["direct", "z3"]
    payload["infrastructure_smoke"] = {
        "selection_path": str(receipt_path),
        "selection_sha256": receipt.selection_sha256,
    }
    return RunConfig.model_validate(payload), parent, receipt_path, receipt


def test_selection_exact_queue_and_no_standalone_admission(smoke):
    config, _, _, receipt = smoke
    ready = preflight(config)
    assert len(receipt.case_uids) == 8
    assert len(ready.jobs) == 16  # 8 selected of 16 parent cases x 2 strategies
    assert {j.case.case_id for j in ready.jobs} == set(receipt.case_uids)
    assert ready.identity["runner_protocol"] == "infrastructure-smoke-v1"
    assert ready.identity["smoke_selection"]["purpose"] == "infrastructure-smoke"
    assert receipt.standalone_research_admission == "not_admitted"
    assert receipt.leakage_status == "not_applicable_infrastructure_subset"
    assert {
        (j.case.metadata["pattern_id"], j.case.is_satisfiable, j.strategy)
        for j in ready.jobs
    } == {
        (pattern, sat, strategy)
        for pattern in ("chain", "math")
        for sat in (False, True)
        for strategy in ("direct", "z3")
    }


@pytest.mark.parametrize("change", ["leakage", "artifact", "confirmation"])
def test_parent_failure_blocks_before_completion(smoke, tmp_path, change):
    config, parent, _, _ = smoke
    payload = json.loads(parent.read_text())
    if change == "leakage":
        payload["cells"][0]["leakage_report"]["global_word"][
            "mean_balanced_accuracy"
        ] = 0.9
        parent.write_text(json.dumps(payload))
    elif change == "artifact":
        (parent.parent / payload["cells"][0]["dataset_path"]).write_text("{}\n")
    else:
        payload["plan"]["purpose"] = "confirmation"
        parent.write_text(json.dumps(payload))
    calls = []
    with pytest.raises(ValueError):
        new_run(config, tmp_path / "blocked", completion=lambda **kw: calls.append(kw))
    assert not calls
    assert not (tmp_path / "blocked").exists()


@pytest.mark.parametrize(
    "change",
    [
        "unknown_uid",
        "other_family",
        "subset",
        "hash",
        "purpose",
        "rule",
        "rehashed_rule",
    ],
)
def test_selection_tampering_blocks_start(smoke, tmp_path, change):
    from logicmus_eval.infrastructure_smoke import selection_digest
    from logicmus_eval.runner.execution import initialize_run

    config, parent, path, receipt = smoke
    initialized = tmp_path / "initialized"
    initialize_run(config, initialized)
    payload = json.loads(path.read_text())
    if change == "unknown_uid":
        payload["case_uids"][0] = "0" * 64
    elif change == "other_family":
        manifest = json.loads(parent.read_text())
        candidates = [
            json.loads(line)["case_id"]
            for line in (parent.parent / manifest["combined_path"])
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        payload["case_uids"][0] = next(
            uid for uid in candidates if uid not in receipt.case_uids
        )
        payload["selection_sha256"] = selection_digest(payload)
    elif change == "subset":
        payload["case_uids"] = payload["case_uids"][:-1]
    elif change == "hash":
        payload["selection_sha256"] = "0" * 64
    elif change == "purpose":
        payload["purpose"] = "confirmation"
    else:
        payload["rule"]["seed"] = 44
        if change == "rehashed_rule":
            payload["selection_sha256"] = selection_digest(payload)
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        new_run(
            config, tmp_path / "blocked", completion=lambda **_: pytest.fail("HTTP")
        )
    with pytest.raises(ValueError):
        resume_run(initialized, completion=lambda **_: pytest.fail("HTTP"))


def test_mock_smoke_resume_diagnostics_and_primary_guard(smoke, tmp_path):
    config, _, _, receipt = smoke
    root = tmp_path / "run"
    calls = []
    jobs = iter(preflight(config).jobs)

    def complete(**kwargs):
        from logicmus_eval.models.rules import (
            FactRule,
            ImpliesRule,
            NoiseRule,
            NumericRule,
            TerminalRule,
        )

        calls.append(kwargs)
        job = next(jobs)
        if job.strategy == "z3":
            classes = {
                "FACT": FactRule,
                "TERMINAL": TerminalRule,
                "NOISE": NoiseRule,
                "IMPLIES": ImpliesRule,
                "NUMERIC_GT": NumericRule,
                "NUMERIC_LT": NumericRule,
                "NUMERIC_EQ": NumericRule,
            }
            rules = [
                classes[rule["operator_type"]].model_validate(rule)
                for rule in job.case.rules
            ]
            numeric = {
                var
                for rule in rules
                if isinstance(rule, NumericRule)
                for var in (rule.left_var, rule.right_var)
            }
            code = [
                "solver = Solver()",
                *(
                    f"{var} = {'Real' if var in numeric else 'Bool'}({var!r})"
                    for var in job.case.predicate_mapping
                ),
            ]
            code.extend(
                f"solver.assert_and_track({rule.to_z3()}, {rule.id!r})"
                for rule in rules
            )
            return answer(
                json.dumps(
                    {
                        "reasoning": "fixture translation",
                        "python_z3_code": "\n".join(code),
                    }
                ),
                usage=False,
            )
        return answer(usage=False)

    report = new_run(config, root, completion=complete)
    assert len(calls) == len(report.details) == 16
    assert all(outcome.error_type is None for outcome in report.details[8:])
    before = read_snapshot(root, [root / "report.json"])
    assert all(
        attempt.intent.invocation_origin == "injected-completion"
        for state in before.states.values()
        for attempt in state.attempts
    )
    assert resume_run(root, completion=lambda **_: pytest.fail("extra HTTP")) == report
    after = read_snapshot(root, [root / "report.json"])
    assert before.journal_head == after.journal_head
    assert (
        before.manifest.payload.identity.smoke_selection.case_uids == receipt.case_uids
    )
    payload = {
        "analysis_version": "controlled-analysis-v1",
        "purpose": "development",
        "mode": "diagnostic",
        "groups": [{"name": "smoke", "run_ids": [before.manifest.payload.run_id]}],
        "intervals": {"seed": 2, "repeats": 20},
    }
    analyze(
        [root],
        AnalysisPlan.model_validate(payload),
        tmp_path / "diagnostics",
        plots=False,
    )
    assert (
        json.loads((tmp_path / "diagnostics/analysis.manifest.json").read_text())[
            "status"
        ]
        == "complete"
    )
    payload["mode"] = "primary"
    with pytest.raises(ValueError, match="[Ii]nfrastructure"):
        analyze(
            [root],
            AnalysisPlan.model_validate(payload),
            tmp_path / "primary",
            plots=False,
        )
    altered = config.model_copy(deep=True)
    altered.models[0].generation.max_tokens += 1
    with pytest.raises(ValueError):
        resume_run(root, config=altered, completion=lambda **_: pytest.fail("HTTP"))


def test_smoke_offline_imports_no_network_client(smoke):
    config, parent, path, _ = smoke
    script = f"""
import sys
from pathlib import Path
from logicmus_eval.infrastructure_smoke import SelectionRule, prepare_selection
from logicmus_eval.runner.config import RunConfig
from logicmus_eval.runner.preflight import preflight
rule = SelectionRule(selection_version='infrastructure-smoke-v1', seed=42, pair_index=0)
prepare_selection(Path({str(parent)!r}), rule, Path({str(path)!r}))
preflight(RunConfig.model_validate_json({config.model_dump_json()!r}))
assert 'logicmus_eval.runner.inference' not in sys.modules
assert 'logicmus_eval.runner.transport' not in sys.modules
assert 'litellm' not in sys.modules
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("field", ["runner_protocol", "smoke_selection", "config"])
def test_saved_smoke_identity_cannot_lose_scope(smoke, field):
    from logicmus_eval.runner.snapshot_models import SavedIdentity

    config, _, _, _ = smoke
    identity = preflight(config).identity
    if field == "runner_protocol":
        identity[field] = "controlled-run-v1"
    elif field == "smoke_selection":
        identity.pop(field)
    else:
        identity[field]["infrastructure_smoke"] = None
    with pytest.raises(ValueError, match="[Ss]moke"):
        SavedIdentity.model_validate(identity)


def test_historical_identity_preserves_absent_new_fields(series):
    from logicmus_eval.runner.snapshot_models import SavedIdentity

    identity = preflight(config_for(series)).identity
    identity.pop("generation_protocol")
    identity["config"].pop("infrastructure_smoke")
    assert SavedIdentity.model_validate(identity).saved_json() == identity


def test_even_admitted_confirmation_parent_cannot_supply_smoke(series, tmp_path):
    from logicmus_eval.infrastructure_smoke import SelectionRule, prepare_selection

    _, manifest = series
    payload = dict(manifest.plan, purpose="confirmation", seeds=[43])
    root = tmp_path / "confirmation-parent"
    admitted = prepare_experiment(ExperimentPlan.model_validate(payload), root)
    assert admitted.ready_for_evaluation
    destination = tmp_path / "forbidden-selection.json"
    with pytest.raises(ValueError, match="development"):
        prepare_selection(
            root / "series.manifest.json",
            SelectionRule(
                selection_version="infrastructure-smoke-v1", seed=43, pair_index=0
            ),
            destination,
        )
    assert not destination.exists()


def test_different_models_cannot_hide_mixed_generation_protocols(series, tmp_path):
    old_root, old_manifest = series
    payload = dict(old_manifest.plan, protocol_version="controlled-v2")
    new_root = tmp_path / "v2-parent"
    new_manifest = prepare_experiment(ExperimentPlan.model_validate(payload), new_root)
    runs = []
    for name, selected in (
        ("old", (old_root, old_manifest)),
        ("new", (new_root, new_manifest)),
    ):
        config = config_for(selected)
        config.models[0].model_id = f"model/{name}"
        run = tmp_path / name
        new_run(config, run, completion=lambda **_: answer())
        runs.append(run)
    ids = [
        json.loads((run / "run.manifest.json").read_text())["payload"]["run_id"]
        for run in runs
    ]
    plan = AnalysisPlan.model_validate(
        {
            "analysis_version": "controlled-analysis-v1",
            "purpose": "development",
            "mode": "primary",
            "groups": [{"name": "mixed", "run_ids": ids}],
            "intervals": {"seed": 2, "repeats": 20},
        }
    )
    with pytest.raises(ValueError, match="[Pp]rotocol"):
        analyze(runs, plan, tmp_path / "mixed-analysis")
