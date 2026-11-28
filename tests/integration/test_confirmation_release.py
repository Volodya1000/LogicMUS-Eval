"""Offline release contracts; tiny datasets and mock responses only."""

# Pytest fixture arguments intentionally use their registered names.
# pylint: disable=redefined-outer-name
import json
import subprocess
import sys

import pytest
from test_controlled_runner import answer, config_for, fixture_series

from logicmus_eval.analysis import analyze
from logicmus_eval.analysis.plan import AnalysisPlan
from logicmus_eval.analysis.sources import load_snapshots
from logicmus_eval.confirmation import binding, launch
from logicmus_eval.confirmation.binding import bind_analysis, verify_binding
from logicmus_eval.confirmation.evidence import _analysis_evidence, check_backend
from logicmus_eval.confirmation.inventory import inventory
from logicmus_eval.confirmation.models import SmokeEvidence
from logicmus_eval.confirmation.prospective import validate_template
from logicmus_eval.confirmation.service import (
    _profile_unknowns,
    contracts,
    freeze_release,
    seal_preparation,
    verify_release,
)
from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.hashing import compute_file_sha256
from logicmus_eval.runner.execution import initialize_run, new_run, resume_run
from logicmus_eval.runner.journal import RunJournal
from logicmus_eval.runner.preflight import preflight
from logicmus_eval.runner.snapshot import read_snapshot

series = fixture_series


def template_for(config, plan):
    model = config.models[0].model_id
    return AnalysisPlan.model_validate(
        {
            "analysis_version": "controlled-analysis-v1",
            "purpose": plan.purpose,
            "groups": [{"name": "main", "run_ids": ["main"]}],
            "contrasts": [
                {
                    "name": "noise",
                    "kind": "noise",
                    "left": {
                        "group": "main",
                        "model_id": model,
                        "strategy": "direct",
                        "N": 4,
                    },
                    "right": {
                        "group": "main",
                        "model_id": model,
                        "strategy": "direct",
                        "N": 7,
                    },
                }
            ],
            "intervals": {"seed": 998, "repeats": 20},
        }
    )


def test_inventory_counts_families_once_and_matches_runner(series):

    config = config_for(series)
    plan = ExperimentPlan.model_validate(series[1].plan)
    counts = inventory(plan, {"main": config})
    assert counts["cells"] == 2
    assert counts["independent_families"] == 2
    assert counts["family_cell_occurrences"] == 4
    assert counts["cases"] == 8
    assert counts["requests"] == len(preflight(config).jobs) == 8
    assert counts["max_attempts"] == 8
    assert counts["output_token_cap"] == 8 * 512
    assert counts["per_cell"][0]["independent_families"] == 2


def test_prospective_template_validates_exact_pairs(series):
    config = config_for(series)
    plan = ExperimentPlan.model_validate(series[1].plan)
    result = validate_template(plan, {"main": config}, template_for(config, plan))
    assert result == {"noise": 2}


@pytest.mark.parametrize(
    "change", ["missing", "ambiguous", "different_model", "duplicate", "wrong_kind"]
)
def test_bad_contrasts_rejected_before_http(series, change):
    config = config_for(series)
    plan = ExperimentPlan.model_validate(series[1].plan)
    payload = template_for(config, plan).model_dump(mode="json")
    if change == "missing":
        payload["contrasts"][0]["right"]["N"] = 100
    elif change == "ambiguous":
        payload["contrasts"][0]["left"]["N"] = None
    elif change == "different_model":
        payload["contrasts"][0]["right"]["model_id"] = "not-in-config"
    elif change == "duplicate":
        payload["groups"][0]["run_ids"] = ["main", "main"]
    else:
        payload["contrasts"][0]["kind"] = "strategy"
    with pytest.raises(ValueError):
        validate_template(plan, {"main": config}, AnalysisPlan.model_validate(payload))


def test_initialize_is_offline_and_binding_only_substitutes_uuid(series, tmp_path):
    # pylint: disable=too-many-locals

    config = config_for(series)
    plan = ExperimentPlan.model_validate(series[1].plan)
    template = template_for(config, plan)
    root = tmp_path / "initialized"
    manifest = initialize_run(config, root)
    with RunJournal(root, manifest["manifest_sha256"], read_only=True) as journal:
        assert not journal.events
    with pytest.raises(FileExistsError):
        initialize_run(config, root)
    destination = tmp_path / "binding"
    receipt = bind_analysis(
        plan, {"main": config}, template, {"main": root}, destination
    )
    bound = AnalysisPlan.model_validate_json(
        (destination / "analysis.bound.json").read_text()
    )
    expected = template.model_dump(mode="json")
    expected["groups"][0]["run_ids"] = [manifest["payload"]["run_id"]]
    assert bound.model_dump(mode="json") == expected
    assert receipt["before_first_http"] is True
    verify_binding(destination, template, {"main": root})
    broken = bound.model_dump(mode="json")
    broken["intervals"]["seed"] += 1
    (destination / "analysis.bound.json").write_text(json.dumps(broken))
    with pytest.raises(ValueError, match="binding"):
        verify_binding(destination, template, {"main": root})


def test_binding_rejects_started_run(series, tmp_path):

    config = config_for(series)
    plan = ExperimentPlan.model_validate(series[1].plan)
    root = tmp_path / "started"
    new_run(config, root, completion=lambda **_: answer(usage=False))
    with pytest.raises(ValueError, match="before first HTTP"):
        bind_analysis(
            plan,
            {"main": config},
            template_for(config, plan),
            {"main": root},
            tmp_path / "bound",
        )
    assert not (tmp_path / "bound").exists()


@pytest.fixture(name="release_root")
def fixture_release_root(series, tmp_path):

    root = tmp_path
    config = config_for(series)
    config.series_manifest = "series/series.manifest.json"
    plan = ExperimentPlan.model_validate(series[1].plan)
    documents = {
        "release.spec.json": {
            "release_version": "confirmation-release-v1",
            "release_id": "test-v1",
            "base_commit": "1" * 40,
            "plan": "plan.json",
            "protocol": "protocol.md",
            "analysis_template": "analysis.json",
            "configs": {"main": "run.json"},
            "development_plans": ["development.json"],
            "smoke_plan": "development.json",
        },
        "plan.json": plan.model_dump(mode="json"),
        "development.json": plan.model_dump(mode="json"),
        "analysis.json": template_for(config, plan).model_dump(mode="json"),
        "run.json": config.model_dump(mode="json"),
    }
    (root / "protocol.md").write_text("Frozen protocol")
    for name, payload in documents.items():
        (root / name).write_text(json.dumps(payload), encoding="utf-8")
    freeze_release(root)
    seal_preparation(root)
    return root


def test_release_separates_data_admission_unknown_profiles_and_missing_smoke(
    release_root,
):

    status = verify_release(release_root)
    assert status["status"] == "blocked"
    assert status["gates"]["scientific_plan_frozen"] == "passed"
    assert status["gates"]["datasets_admitted"] == "passed"
    assert status["gates"]["configurations_complete"] == "blocked"
    assert status["gates"]["real_smoke"] == "not_verified"
    assert status["gates"]["ready_for_scale"] == "blocked"


@pytest.mark.parametrize(
    "name",
    [
        "plan.json",
        "run.json",
        "analysis.json",
        "protocol.md",
        "series/combined_controlled.jsonl",
    ],
)
def test_changed_release_artifact_blocks(release_root, name):

    path = release_root / name
    path.write_bytes(path.read_bytes() + b" ")
    assert verify_release(release_root)["status"] == "blocked"
    assert any("changed" in issue for issue in verify_release(release_root)["issues"])


def test_failed_dataset_cannot_be_sealed_as_admitted(release_root):

    path = release_root / "series/series.manifest.json"
    payload = json.loads(path.read_text())
    payload["ready_for_evaluation"] = False
    path.write_text(json.dumps(payload))
    status = verify_release(release_root)
    assert status["gates"]["datasets_admitted"] == "blocked"


def test_fake_smoke_pass_flag_is_rejected(release_root):

    (release_root / "smoke.evidence.json").write_text('{"main":{"passed":true}}')
    assert verify_release(release_root)["gates"]["real_smoke"] == "not_verified"


def test_release_checks_and_initialization_do_not_import_network(release_root):

    child = """
import importlib.abc, sys
class NoNetwork(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname in {'litellm', 'logicmus_eval.extractor', 'logicmus_eval.runner.inference', 'logicmus_eval.runner.transport'}:
            raise AssertionError('Network import: ' + fullname)
sys.meta_path.insert(0, NoNetwork())
from pathlib import Path
from logicmus_eval.confirmation.service import verify_release, contracts
from logicmus_eval.runner.execution import initialize_run
root = Path(sys.argv[1])
assert verify_release(root)['status'] == 'blocked'
initialize_run(contracts(root)[2]['main'], root / 'offline-run')
"""
    result = subprocess.run(
        [sys.executable, "-c", child, str(release_root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_mock_path_initialize_bind_resume_verify_analyze(series, tmp_path):

    config = config_for(series)
    plan = ExperimentPlan.model_validate(series[1].plan)
    template = template_for(config, plan)
    root = tmp_path / "mock-run"
    initialize_run(config, root)
    bind_analysis(plan, {"main": config}, template, {"main": root}, tmp_path / "bound")
    resume_run(root, completion=lambda **_: answer(usage=False))
    verify_binding(tmp_path / "bound", template, {"main": root})
    assert len(load_snapshots([root])[0].report.details) == 8
    bound = AnalysisPlan.model_validate_json(
        (tmp_path / "bound/analysis.bound.json").read_text()
    )
    analyze([root], bound, tmp_path / "analysis")
    assert (
        json.loads((tmp_path / "analysis/analysis.manifest.json").read_text())["status"]
        == "complete"
    )


def test_family_reuse_across_series_is_not_independent(series):
    config = config_for(series)
    plan = ExperimentPlan.model_validate(series[1].plan)
    payload = plan.model_dump(mode="json")
    repeated = dict(payload["series"][0], series_id="same-conflicts-in-another-series")
    payload["series"].append(repeated)
    result = inventory(ExperimentPlan.model_validate(payload), {"main": config})
    assert result["cells"] == 4
    assert result["cases"] == 16
    assert result["independent_families"] == 2
    assert result["family_cell_occurrences"] == 8


def test_placeholder_profile_cannot_be_complete(series):

    config = config_for(series)
    profile = config.models[0].expected_profile
    profile.served_model_id = "test-model"
    profile.revision = "TODO-exact-revision"
    profile.quantization = "Q4_K_M"
    profile.context_tokens = 4096
    profile.backend_version = "test-backend-1"
    profile.chat_template = "sha256:abcdef"
    profile.tokenizer = "sha256:abcdef"
    assert any("placeholder" in issue for issue in _profile_unknowns({"main": config}))


@pytest.mark.parametrize("calibration_kind", ["empty", "truncated", "timeout"])
def test_backend_rejects_empty_development_calibration(release_root, calibration_kind):

    spec, _, configs, _ = contracts(release_root)
    config = configs["main"]
    config.models[0].expected_profile.context_tokens = 4096
    if calibration_kind == "empty":
        initialize_run(config, release_root / "calibration")
    elif calibration_kind == "truncated":
        new_run(
            config,
            release_root / "calibration",
            completion=lambda **_: answer(finish="length"),
        )
    else:

        def timeout(**_):
            raise TimeoutError

        new_run(config, release_root / "calibration", completion=timeout)
    evidence = {
        "config_sha256": compute_file_sha256(release_root / "run.json"),
        "checked_by": "test operator",
        "checked_at": "2026-11-28",
        "method": "test evidence",
        "artifacts": {"protocol.md": compute_file_sha256(release_root / "protocol.md")},
        "requests_sha256": preflight(config).identity["requests_sha256"],
        "max_input_tokens": 100,
        "tokenizer_and_chat_template_verified": True,
        "generation_and_timeout_verified": True,
        "development_calibration_run": "calibration",
    }
    (release_root / "backend.evidence.json").write_text(json.dumps({"main": evidence}))
    with pytest.raises(ValueError, match="complete|attempt|calibration"):
        check_backend(release_root, spec, configs)


def test_group_incompatibility_without_contrasts_rejected(series):
    config = config_for(series)
    plan = ExperimentPlan.model_validate(series[1].plan)
    changed = config.model_copy(deep=True)
    changed.strategies = ["z3"]
    changed.models[0].generation.max_tokens = 1024
    payload = template_for(config, plan).model_dump(mode="json")
    payload["groups"][0]["run_ids"] = ["direct", "z3"]
    payload["contrasts"] = []
    with pytest.raises(ValueError, match="Incompatible"):
        validate_template(
            plan,
            {"direct": config, "z3": changed},
            AnalysisPlan.model_validate(payload),
        )


def test_stub_smoke_analysis_is_not_evidence(release_root):

    analysis = release_root / "fake-analysis"
    analysis.mkdir()
    plan = {
        "analysis_version": "controlled-analysis-v1",
        "purpose": "development",
        "mode": "legacy",
        "groups": [{"name": "fake", "run_ids": ["some-uuid"]}],
        "intervals": {"seed": 42},
    }
    (analysis / "analysis.manifest.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "plan": plan,
                "inputs": [{"run_id": "some-uuid"}],
                "artifacts": {},
            }
        )
    )
    evidence = SmokeEvidence(
        run_dir="missing",
        attested_real_http=True,
        checked_by="test",
        checked_at="test",
        resume_before_report="before",
        resume_after_report="after",
        analysis_dir="fake-analysis",
        longest_input_accounting="counts.json",
        artifacts={"counts.json": "abc"},
    )
    with pytest.raises(ValueError):
        _analysis_evidence(release_root, evidence, "some-uuid")


def test_binding_holds_all_locks_until_saved(series, tmp_path, monkeypatch):

    config = config_for(series)
    plan = ExperimentPlan.model_validate(series[1].plan)
    root = tmp_path / "initialized"
    initialize_run(config, root)
    original = binding.atomic_json
    seen = []

    def write_while_competing(path, value):
        if path.name == "analysis.bound.json":
            with pytest.raises(ValueError, match="Another writer"):
                resume_run(root, completion=lambda **_: seen.append("HTTP"))
        original(path, value)

    monkeypatch.setattr(binding, "atomic_json", write_while_competing)
    binding.bind_analysis(
        plan,
        {"main": config},
        template_for(config, plan),
        {"main": root},
        tmp_path / "bound",
    )
    assert not seen


def test_gated_resume_preserves_explicit_indeterminate_policy(
    series, tmp_path, monkeypatch
):

    config = config_for(series)
    root = tmp_path / "release"
    run = root / "bundle/runs/main"
    initialize_run(config, run)
    monkeypatch.setattr(launch, "check_admission", lambda _: None)
    monkeypatch.setattr(
        launch, "verify_release", lambda _: {"gates": {"ready_for_scale": "passed"}}
    )
    monkeypatch.setattr(
        launch, "contracts", lambda _: (None, None, {"main": config}, None)
    )
    calls = []

    def interrupted(**_):
        calls.append(1)
        if len(calls) == 2:
            raise KeyboardInterrupt
        return answer(usage=False)

    with pytest.raises(KeyboardInterrupt):
        launch.resume_release(root, "main", completion=interrupted)
    with pytest.raises(ValueError, match="indeterminate"):
        launch.resume_release(root, "main", completion=interrupted)
    assert len(calls) == 2
    launch.resume_release(
        root, "main", completion=interrupted, indeterminate_policy="retry"
    )
    saved = read_snapshot(run.resolve(), [run.resolve() / "report.json"])
    assert len(saved.reports[run.resolve() / "report.json"].details) == 8
    assert len(calls) == 9  # one indeterminate attempt, no repeated finalized jobs


def test_verified_smoke_analysis_then_stale_provenance_rejected(series, tmp_path):

    run = tmp_path / "mock-run"
    new_run(config_for(series), run, completion=lambda **_: answer(usage=False))
    run_id = json.loads((run / "run.manifest.json").read_text())["payload"]["run_id"]
    plan = AnalysisPlan.model_validate(
        {
            "analysis_version": "controlled-analysis-v1",
            "purpose": "development",
            "groups": [{"name": "smoke", "run_ids": [run_id]}],
            "intervals": {"seed": 42, "repeats": 20},
        }
    )
    analyze([run], plan, tmp_path / "smoke-analysis")
    evidence = SmokeEvidence(
        run_dir="mock-run",
        attested_real_http=True,
        checked_by="test",
        checked_at="test",
        resume_before_report="before",
        resume_after_report="after",
        analysis_dir="smoke-analysis",
        longest_input_accounting="counts.json",
        artifacts={"counts.json": "abc"},
    )
    _analysis_evidence(tmp_path, evidence, run_id)
    path = tmp_path / "smoke-analysis/analysis.manifest.json"
    manifest = json.loads(path.read_text())
    manifest["inputs"][0]["journal_head_sha256"] = "stale"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="provenance"):
        _analysis_evidence(tmp_path, evidence, run_id)
