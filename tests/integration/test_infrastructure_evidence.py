"""Infrastructure evidence keeps diagnosis distinct from research admission."""

# Fixtures and focused evidence-boundary tests intentionally share registered names.
# pylint: disable=redefined-outer-name,protected-access

import json
import shutil
from pathlib import Path

import pytest
import typer
from test_confirmation_release import fixture_release_root
from test_controlled_runner import answer, config_for, fixture_series
from test_infrastructure_smoke import fixture_smoke
from typer.testing import CliRunner

from logicmus_eval.analysis import analyze
from logicmus_eval.analysis.plan import AnalysisPlan
from logicmus_eval.commands.infrastructure_smoke import check_smoke_evidence
from logicmus_eval.confirmation import evidence as evidence_module
from logicmus_eval.confirmation import infrastructure_evidence as infrastructure_module
from logicmus_eval.confirmation.evidence import _analysis_evidence
from logicmus_eval.confirmation.models import ReleaseSpec, SmokeEvidence
from logicmus_eval.confirmation.service import contracts, freeze_release, verify_release
from logicmus_eval.hashing import compute_file_sha256
from logicmus_eval.runner.execution import new_run, resume_run
from logicmus_eval.runner.preflight import digest, preflight
from logicmus_eval.runner.snapshot import read_snapshot

series = fixture_series
smoke = fixture_smoke
release_root = fixture_release_root


def infrastructure_evidence(**changes):
    payload = {
        "evidence_version": "infrastructure-smoke-v1",
        "run_dir": "run",
        "attested_real_http": True,
        "checked_by": "test operator",
        "checked_at": "2026-11-28",
        "resume_before_report": "before.json",
        "resume_after_report": "after.json",
        "analysis_dir": "analysis",
        "longest_input_accounting": "accounting.json",
        "parent_manifest_sha256": "a" * 64,
        "selection_sha256": "b" * 64,
        "artifacts": {"accounting.json": "c" * 64},
    }
    payload.update(changes)
    return SmokeEvidence.model_validate(payload)


@pytest.mark.parametrize("mode", ["diagnostic", "primary"])
def test_infrastructure_evidence_requires_diagnostic_analysis(series, tmp_path, mode):
    run = tmp_path / "run"
    new_run(config_for(series), run, completion=lambda **_: answer(usage=False))
    run_id = json.loads((run / "run.manifest.json").read_text())["payload"]["run_id"]
    plan = AnalysisPlan.model_validate(
        {
            "analysis_version": "controlled-analysis-v1",
            "purpose": "development",
            "mode": mode,
            "groups": [{"name": "smoke", "run_ids": [run_id]}],
            "intervals": {"seed": 42, "repeats": 20},
        }
    )
    analyze([run], plan, tmp_path / "analysis")
    evidence = infrastructure_evidence()
    if mode == "diagnostic":
        _analysis_evidence(tmp_path, evidence, run_id)
    else:
        with pytest.raises(ValueError, match="diagnostic"):
            _analysis_evidence(tmp_path, evidence, run_id)


@pytest.mark.parametrize("field", ["parent_manifest_sha256", "selection_sha256"])
def test_infrastructure_evidence_requires_parent_and_selection_hashes(field):
    with pytest.raises(ValueError, match="parent|selection"):
        infrastructure_evidence(**{field: None})


@pytest.mark.parametrize(
    "change",
    [
        None,
        "missing_request",
        "wrong_request",
        "uncovered",
        "unknown_context",
        "inconsistent_overlap",
    ],
)
def test_token_accounting_covers_every_exact_request(series, tmp_path, change):
    config = config_for(series)
    config.models[0].expected_profile.context_tokens = 4096
    config.models[0].expected_profile.tokenizer = "test-tokenizer"
    config.models[0].expected_profile.chat_template = "test-template"
    ready = preflight(config)
    measurements = [
        {"request_sha256": digest(job.request), "input_tokens": 100}
        for job in ready.jobs
    ]
    account = {
        "accounting_version": "infrastructure-input-accounting-v1",
        "target_requests_sha256": ready.identity["requests_sha256"],
        "smoke_requests_sha256": ready.identity["requests_sha256"],
        "parent_manifest_sha256": "a" * 64,
        "selection_sha256": "b" * 64,
        "measurements": [
            {
                "model_id": config.models[0].model_id,
                "strategy": "direct",
                "tokenizer": "test-tokenizer",
                "chat_template": "test-template",
                "target": measurements,
                "smoke": [dict(item) for item in measurements],
            }
        ],
    }
    if change == "missing_request":
        account["measurements"][0]["target"] = measurements[:-1]
    elif change == "wrong_request":
        account["measurements"][0]["smoke"][0]["request_sha256"] = "d" * 64
    elif change == "uncovered":
        account["measurements"][0]["target"][0]["input_tokens"] = 101
    elif change == "unknown_context":
        ready.config.models[0].expected_profile.context_tokens = None
    elif change == "inconsistent_overlap":
        account["measurements"][0]["smoke"][0]["input_tokens"] = 101
    (tmp_path / "accounting.json").write_text(json.dumps(account))
    evidence = infrastructure_evidence()
    if change is None:
        infrastructure_module._input_accounting(tmp_path, evidence, ready, ready)
    else:
        with pytest.raises(ValueError, match="accounting|coverage|context"):
            infrastructure_module._input_accounting(tmp_path, evidence, ready, ready)


def test_admitted_mock_pipeline_never_becomes_real_smoke_evidence(smoke, tmp_path):
    # pylint: disable=too-many-locals
    config, parent, selection_path, receipt = smoke
    profile = config.models[0].expected_profile
    profile.context_tokens = 4096
    profile.tokenizer = "test-tokenizer"
    profile.chat_template = "test-template"
    run = tmp_path / "run"
    report = new_run(config, run, completion=lambda **_: answer(usage=False))
    assert len(report.details) == 16
    shutil.copyfile(run / "report.json", run / "before.json")
    resume_run(run, completion=lambda **_: pytest.fail("no-op resume sent HTTP"))
    shutil.copyfile(run / "report.json", run / "after.json")
    run_id = json.loads((run / "run.manifest.json").read_text())["payload"]["run_id"]
    analyze(
        [run],
        AnalysisPlan.model_validate(
            {
                "analysis_version": "controlled-analysis-v1",
                "purpose": "development",
                "mode": "diagnostic",
                "groups": [{"name": "smoke", "run_ids": [run_id]}],
                "intervals": {"seed": 42, "repeats": 20},
            }
        ),
        tmp_path / "analysis",
    )
    ready = preflight(config)
    target_config = config.model_copy(deep=True)
    target_config.infrastructure_smoke = None
    target = preflight(target_config)
    accounting = {
        "accounting_version": "infrastructure-input-accounting-v1",
        "target_requests_sha256": target.identity["requests_sha256"],
        "smoke_requests_sha256": ready.identity["requests_sha256"],
        "parent_manifest_sha256": receipt.parent_manifest_sha256,
        "selection_sha256": receipt.selection_sha256,
        "measurements": [
            {
                "model_id": config.models[0].model_id,
                "strategy": strategy,
                "tokenizer": "test-tokenizer",
                "chat_template": "test-template",
                "target": [
                    {"request_sha256": digest(job.request), "input_tokens": 100}
                    for job in target.jobs
                    if job.strategy == strategy
                ],
                "smoke": [
                    {"request_sha256": digest(job.request), "input_tokens": 100}
                    for job in ready.jobs
                    if job.strategy == strategy
                ],
            }
            for strategy in config.strategies
        ],
    }
    (tmp_path / "accounting.json").write_text(json.dumps(accounting))
    required = [
        parent,
        selection_path,
        run / "run.manifest.json",
        run / "journal.sqlite3",
        run / "before.json",
        run / "after.json",
        tmp_path / "accounting.json",
        tmp_path / "analysis/analysis.manifest.json",
    ]
    evidence = infrastructure_evidence(
        parent_manifest_sha256=receipt.parent_manifest_sha256,
        selection_sha256=receipt.selection_sha256,
        resume_before_report="run/before.json",
        resume_after_report="run/after.json",
        artifacts={
            path.relative_to(tmp_path).as_posix(): compute_file_sha256(path)
            for path in required
        },
    )
    evidence_module._analysis_evidence(tmp_path, evidence, run_id)
    with pytest.raises(ValueError, match="Real HTTP|mock"):
        infrastructure_module.check_development_smoke(tmp_path, config, evidence)
    (tmp_path / "parent.plan.json").write_text(
        json.dumps(json.loads(parent.read_text())["plan"])
    )
    (tmp_path / "smoke.rule.json").write_text(receipt.rule.model_dump_json())
    (tmp_path / "smoke.evidence.json").write_text(
        json.dumps({"main": evidence.model_dump(mode="json")})
    )
    spec = ReleaseSpec(
        release_version="confirmation-release-v1",
        release_id="test",
        base_commit="1" * 40,
        plan="parent.plan.json",
        protocol="unused",
        analysis_template="unused",
        configs={"main": "unused"},
        development_plans=["parent.plan.json"],
        smoke_plan="parent.plan.json",
        smoke_selection_rule="smoke.rule.json",
    )
    with pytest.raises(ValueError, match="Real HTTP|mock"):
        evidence_module.check_smoke(tmp_path, spec, {"main": target_config})
    changed = receipt.rule.model_copy(update={"seed": 44})
    (tmp_path / "smoke.rule.json").write_text(changed.model_dump_json())
    with pytest.raises(ValueError, match="frozen|selection"):
        evidence_module.check_smoke(tmp_path, spec, {"main": target_config})


def test_release_admission_rejects_infrastructure_config(release_root):
    path = release_root / "run.json"
    payload = json.loads(path.read_text())
    payload["infrastructure_smoke"] = {
        "selection_path": "selection.json",
        "selection_sha256": "a" * 64,
    }
    payload["strategies"] = ["direct", "z3"]
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="datasets_admitted"):
        contracts(release_root)


def test_new_release_freezes_rule_and_rejects_changes(release_root):
    spec_path = release_root / "release.spec.json"
    payload = json.loads(spec_path.read_text())
    payload["smoke_selection_rule"] = "smoke.rule.json"
    spec_path.write_text(json.dumps(payload))
    rule = release_root / "smoke.rule.json"
    rule.write_text(
        json.dumps(
            {
                "selection_version": "infrastructure-smoke-v1",
                "seed": 42,
                "pair_index": 0,
            }
        )
    )
    (release_root / "release.manifest.json").unlink()
    frozen = freeze_release(release_root)
    assert frozen["files"]["smoke.rule.json"] == compute_file_sha256(rule)
    rule.write_text(rule.read_text() + " ")
    status = verify_release(release_root)
    assert status["gates"]["scientific_plan_frozen"] == "blocked"
    assert status["gates"]["datasets_admitted"] == "blocked"


def test_development_contract_fixed_before_preparation():
    root = Path(__file__).resolve().parents[2] / "configs/development-smoke-v2"
    frozen = json.loads((root / "protocol.freeze.json").read_text())
    for name, checksum in frozen["files"].items():
        assert compute_file_sha256(root / name) == checksum
    plan = json.loads((root / "parent.plan.json").read_text())
    rule = json.loads((root / "selection.rule.json").read_text())
    assert plan["seeds"] == [424242, 424244]
    assert plan["pairs_per_seed"] == 128
    assert rule == {
        "selection_version": "infrastructure-smoke-v1",
        "seed": 424242,
        "pair_index": 0,
    }
    assert frozen["parent_cases"] == 2048
    assert frozen["smoke_cases"] == 8
    assert frozen["planned_requests"] == 48


def test_evidence_cli_without_http_stays_not_verified(tmp_path):
    app = typer.Typer()
    app.command()(check_smoke_evidence)
    result = CliRunner().invoke(
        app,
        [
            "--root",
            str(tmp_path),
            "--config",
            str(tmp_path / "missing-config.json"),
            "--evidence",
            str(tmp_path / "missing-evidence.json"),
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.stdout)["real_smoke"] == "not_verified"


def forged_http_answer(**_):
    response = answer(usage=False)
    response["http_status"] = 200
    response["raw_body"] = json.dumps(response)
    return response


def test_injected_http_envelopes_cannot_verify_real_smoke(smoke, tmp_path):
    config, _, _, _ = smoke
    run = tmp_path / "forged"
    new_run(config, run, completion=forged_http_answer)
    snapshot = read_snapshot(run, [run / "report.json"])
    assert all(
        state.attempts[0].intent.invocation_origin == "injected-completion"
        for state in snapshot.states.values()
    )
    with pytest.raises(ValueError, match="Real HTTP|mock"):
        infrastructure_module._real_http(snapshot)


def test_backend_rejects_injected_legacy_calibration(release_root):
    spec, _, configs, _ = contracts(release_root)
    config = configs["main"]
    config.models[0].expected_profile.context_tokens = 4096
    new_run(config, release_root / "calibration", completion=forged_http_answer)
    (release_root / "backend.evidence.json").write_text(
        json.dumps(
            {
                "main": {
                    "config_sha256": compute_file_sha256(release_root / "run.json"),
                    "checked_by": "test",
                    "checked_at": "2026-11-28",
                    "method": "test",
                    "artifacts": {
                        "protocol.md": compute_file_sha256(release_root / "protocol.md")
                    },
                    "requests_sha256": preflight(config).identity["requests_sha256"],
                    "max_input_tokens": 100,
                    "tokenizer_and_chat_template_verified": True,
                    "generation_and_timeout_verified": True,
                    "development_calibration_run": "calibration",
                }
            }
        )
    )
    with pytest.raises(ValueError, match="Real HTTP|mock"):
        evidence_module.check_backend(release_root, spec, configs)


def test_legacy_smoke_cannot_upgrade_injected_http_envelopes(smoke, tmp_path):
    # pylint: disable=too-many-locals
    config, parent, _, _ = smoke
    config.infrastructure_smoke = None
    run = tmp_path / "legacy-run"
    new_run(config, run, completion=forged_http_answer)
    shutil.copyfile(run / "report.json", run / "before.json")
    resume_run(run, completion=lambda **_: pytest.fail("no-op HTTP"))
    shutil.copyfile(run / "report.json", run / "after.json")
    snapshot = read_snapshot(run, [run / "report.json"])
    analyze(
        [run],
        AnalysisPlan.model_validate(
            {
                "analysis_version": "controlled-analysis-v1",
                "purpose": "development",
                "groups": [
                    {"name": "smoke", "run_ids": [snapshot.manifest.payload.run_id]}
                ],
                "intervals": {"seed": 42, "repeats": 20},
            }
        ),
        tmp_path / "legacy-analysis",
    )
    plan = json.loads(parent.read_text())["plan"]
    plan_path = tmp_path / "parent.plan.json"
    plan_path.write_text(json.dumps(plan))
    request_hash = preflight(config).identity["requests_sha256"]
    (tmp_path / "accounting.json").write_text(
        json.dumps(
            {
                "confirmation_requests_sha256": request_hash,
                "smoke_requests_sha256": request_hash,
                "smoke_max_input_tokens": 100,
                "confirmation_max_input_tokens": 100,
            }
        )
    )
    artifacts = [
        plan_path,
        tmp_path / "accounting.json",
        run / "before.json",
        run / "after.json",
    ]
    document = {
        "run_dir": "legacy-run",
        "attested_real_http": True,
        "checked_by": "test",
        "checked_at": "2026-11-28",
        "resume_before_report": "legacy-run/before.json",
        "resume_after_report": "legacy-run/after.json",
        "analysis_dir": "legacy-analysis",
        "longest_input_accounting": "accounting.json",
        "artifacts": {
            path.relative_to(tmp_path).as_posix(): compute_file_sha256(path)
            for path in artifacts
        },
    }
    (tmp_path / "smoke.evidence.json").write_text(json.dumps({"main": document}))
    spec = ReleaseSpec(
        release_version="confirmation-release-v1",
        release_id="test",
        base_commit="1" * 40,
        plan="parent.plan.json",
        protocol="unused",
        analysis_template="unused",
        configs={"main": "unused"},
        development_plans=["parent.plan.json"],
        smoke_plan="parent.plan.json",
    )
    with pytest.raises(ValueError, match="Real HTTP|mock"):
        evidence_module.check_smoke(tmp_path, spec, {"main": config})
