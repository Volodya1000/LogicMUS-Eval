import json
import subprocess
import sys

import pytest
from pydantic import ValidationError

from logicmus_eval import experiment_preparation
from logicmus_eval.enums import EvaluationErrorType
from logicmus_eval.evaluation.reports import verify_runner_report
from logicmus_eval.evaluation.strategies.direct import DirectEvaluationStrategy
from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.experiment_preparation import prepare_experiment
from logicmus_eval.models.evaluation import Z3ExecutionResult
from logicmus_eval.models.manifests import TfidfMetrics
from logicmus_eval.models.pipeline import LeakageReport
from logicmus_eval.runner import preflight as preflight_module
from logicmus_eval.runner import transport
from logicmus_eval.runner.config import RunConfig
from logicmus_eval.runner.execution import new_run, resume_run
from logicmus_eval.runner.journal import RunJournal
from logicmus_eval.runner.preflight import preflight
from logicmus_eval.runner.transport import TransportError
from logicmus_eval.sandbox.executor import Z3CodeExecutor


@pytest.fixture(name="series")
def fixture_series(tmp_path, monkeypatch):
    def measured_probe(_dataset, ks):
        metric = TfidfMetrics(
            mean_balanced_accuracy=0.5,
            status="ok",
            n_splits=2,
            fold_balanced_accuracies=[0.5, 0.5],
        )
        groups = {
            name: {"word_tfidf": metric, "char_tfidf": metric}
            for name in ["global", *(f"mus_size={k}" for k in ks)]
        }
        return LeakageReport(
            global_word=metric,
            global_char=metric,
            by_mus_size={k: v for k, v in groups.items() if k != "global"},
            by_input={"direct": groups, "z3": groups},
        )

    monkeypatch.setattr(experiment_preparation, "calculate_leakage", measured_probe)
    plan = ExperimentPlan.model_validate(
        {
            "protocol_version": "controlled-v1",
            "purpose": "development",
            "seeds": [42],
            "pairs_per_seed": 2,
            "series": [
                {
                    "series_id": "tiny",
                    "kind": "noise_sweep",
                    "patterns": [{"pattern_id": "fork", "k_values": [3]}],
                    "n_values": [4, 7],
                }
            ],
        }
    )
    root = tmp_path / "series"
    manifest = prepare_experiment(plan, root)
    assert manifest.ready_for_evaluation
    return root, manifest


def config_for(series):

    root, _ = series
    return RunConfig.model_validate(
        {
            "config_version": "controlled-run-v1",
            "series_manifest": str(root / "series.manifest.json"),
            "endpoint": "http://localhost:1234/v1",
            "models": [
                {
                    "model_id": "openai/test-model",
                    "expected_profile": {},
                    "generation": {"max_tokens": 512, "temperature": 0.0},
                }
            ],
            "strategies": ["direct"],
            "request_timeout_seconds": 5.0,
            "retry": {
                "max_attempts": 1,
                "initial_delay_seconds": 0.0,
                "max_delay_seconds": 0.0,
                "transient_errors": ["api_timeout", "api_connection", "api_rate_limit"],
            },
            "z3_timeout_seconds": 2.0,
        }
    )


def test_preflight_exact_inventory_and_unknowns(series):

    ready = preflight(config_for(series))
    assert len(ready.jobs) == 8  # 2 cells x 2 pairs x SAT/UNSAT
    assert len({job.job_id for job in ready.jobs}) == 8
    assert sorted(ready.counts.values()) == [4, 4]
    assert any("context" in warning for warning in ready.unknowns)
    assert ready.identity["source_bundle_sha256"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("api_key", "secret"),
        ("authorization", "secret"),
        ("unknown_setting", 1),
        ("endpoint", "https://user:secret@example.com/v1"),
    ],
)
def test_config_rejects_unrecorded_or_secret_conditions(series, field, value):

    payload = config_for(series).model_dump(mode="json")
    payload[field] = value
    with pytest.raises(ValidationError):
        RunConfig.model_validate(payload)


def test_output_budget_is_required(series):

    payload = config_for(series).model_dump(mode="json")
    del payload["models"][0]["generation"]["max_tokens"]
    with pytest.raises(ValidationError):
        RunConfig.model_validate(payload)


def test_failed_whole_series_blocks_preflight(series):

    root, manifest = series
    manifest.ready_for_evaluation = False
    (root / "series.manifest.json").write_text(
        manifest.model_dump_json(), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="not approved"):
        preflight(config_for(series))


def test_offline_preflight_never_imports_network_client(series, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(config_for(series).model_dump_json(), encoding="utf-8")
    child = """
import importlib.abc, sys
class NoNetwork(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname in {'litellm', 'logicmus_eval.extractor', 'logicmus_eval.runner.inference'}:
            raise AssertionError('Network import: ' + fullname)
sys.meta_path.insert(0, NoNetwork())
from typer.testing import CliRunner
from logicmus_eval.cli import app
r = CliRunner().invoke(app, ['experiment-preflight', '--config', sys.argv[1]])
assert r.exit_code == 0, r.output + str(r.exception)
assert '8' in r.output
"""
    result = subprocess.run(
        [sys.executable, "-c", child, str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def answer(content=None, *, finish="stop", usage=True):
    return {
        "id": "response-123",
        "model": "test-model",
        "created": 1,
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {
                    "role": "assistant",
                    "content": content
                    or json.dumps(
                        {
                            "reasoning": "ok",
                            "is_sat": True,
                            "conflict_core": [],
                        }
                    ),
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        if usage
        else None,
    }


def test_resume_only_remaining_and_matches_persisted_metrics(series, tmp_path):

    config = config_for(series)
    calls = []

    def stop(**request):
        calls.append(request)
        if len(calls) == 4:
            raise KeyboardInterrupt
        return answer()

    root = tmp_path / "run"
    with pytest.raises(KeyboardInterrupt):
        new_run(config, root, completion=stop)
    partial = json.loads((root / "report.json").read_text(encoding="utf-8"))
    assert partial["metrics"]["processed"] == 3
    assert partial["status"] == "running"
    # Intent for call 4 was committed. Default policy cannot silently resend it.
    with pytest.raises(ValueError, match="indeterminate"):
        resume_run(root, completion=lambda **_: pytest.fail("unexpected HTTP"))
    remaining = []

    def complete(**request):
        remaining.append(request)
        return answer()

    resumed = resume_run(root, indeterminate_policy="retry", completion=complete)
    assert len(remaining) == 5
    assert resumed.metrics["processed"] == resumed.metrics["planned"] == 8
    assert resumed.status.value == "completed"
    assert resumed.runner_provenance["indeterminate_attempts"] == 1
    assert resumed.details[3].metadata.llm_latency_seconds is None
    assert resumed.metrics["token_accounting_complete"] is False
    again = resume_run(root, completion=lambda **_: pytest.fail("completed case HTTP"))
    assert again.metrics == resumed.metrics
    full = new_run(config, tmp_path / "full", completion=lambda **_: answer())
    # Durations and uncertain cost intentionally differ; accuracy denominators do not.
    for key in (
        "planned",
        "processed",
        "valid_responses_evaluated",
        "sat_accuracy",
        "response_error_rate",
    ):
        assert full.metrics.get(key) == resumed.metrics.get(key)


def test_errors_and_refusals_are_final_outcomes(series, tmp_path):

    responses = iter(
        [
            answer("not JSON"),
            {
                "choices": [
                    {"finish_reason": "stop", "message": {"refusal": "I cannot answer"}}
                ]
            },
            *[answer() for _ in range(6)],
        ]
    )
    root = tmp_path / "run"
    report = new_run(config_for(series), root, completion=lambda **_: next(responses))
    assert report.details[0].error_type.value == "json_error"
    assert report.details[1].refusal
    assert report.metrics["processed"] == 8
    repeated = resume_run(root, completion=lambda **_: pytest.fail("HTTP"))
    assert repeated.metrics == report.metrics


def test_saved_response_replayed_without_http_or_duplicate_usage(
    series, tmp_path, monkeypatch
):

    original = RunJournal.append

    def fail_final(self, event):
        if event["kind"] == "finalized":
            raise KeyboardInterrupt
        return original(self, event)

    root = tmp_path / "run"
    monkeypatch.setattr(RunJournal, "append", fail_final)
    with pytest.raises(KeyboardInterrupt):
        new_run(config_for(series), root, completion=lambda **_: answer())
    monkeypatch.setattr(RunJournal, "append", original)
    calls = []

    def remaining(**request):
        calls.append(request)
        return answer()

    report = resume_run(root, completion=remaining)
    assert len(calls) == 7
    assert report.metrics["total_tokens_consumed"] == 120
    assert report.details[0].metadata.case_latency_seconds is None
    assert len(report.details) == 8


@pytest.mark.parametrize(
    "mutation",
    [
        "model",
        "parameters",
        "dataset",
        "source",
        "prompt",
        "protocol",
        "metrics",
        "schema",
    ],
)
def test_incompatible_resume_blocks_before_http(
    series, tmp_path, monkeypatch, mutation
):

    root = tmp_path / "run"
    config = config_for(series)
    new_run(config, root, completion=lambda **_: answer())
    if mutation == "model":
        config.models[0].model_id = "another"
    elif mutation == "parameters":
        config.models[0].generation.max_tokens = 1000
    elif mutation == "dataset":
        series_root, manifest = series
        with (series_root / manifest.cells[0].dataset_path).open("a") as stream:
            stream.write("\n")
    elif mutation == "source":
        monkeypatch.setattr(
            preflight_module, "compute_source_bundle_hash", lambda: "changed"
        )
    elif mutation == "prompt":
        monkeypatch.setattr(
            DirectEvaluationStrategy, "build_prompt", lambda *_: "changed"
        )
    elif mutation == "protocol":
        monkeypatch.setattr(
            preflight_module, "Z3_EXECUTION_PROTOCOL_VERSION", "changed"
        )
    elif mutation == "metrics":
        monkeypatch.setattr(preflight_module, "METRIC_DEFINITIONS_VERSION", "changed")
    else:
        monkeypatch.setattr(
            preflight_module.DirectReasoningResponse,
            "model_json_schema",
            lambda: {"changed": True},
        )
    with pytest.raises(ValueError):
        resume_run(root, config=config, completion=lambda **_: pytest.fail("HTTP"))


def test_finish_length_unknown_usage_and_recorded_request(series, tmp_path):

    calls = []

    def truncated(**request):
        calls.append(request)
        return answer('{"reasoning":', finish="length", usage=False)

    report = new_run(config_for(series), tmp_path / "run", completion=truncated)
    assert report.details[0].error_type.value == "generation_truncated"
    assert report.details[0].metadata.finish_reason == "length"
    assert report.metrics["total_tokens_consumed"] is None
    assert report.metrics["processed"] == 8
    trace = report.details[0].inference
    assert trace["request"]["body"]["messages"] == calls[0]["body"]["messages"]
    assert trace["request"]["body"]["max_tokens"] == 512
    assert trace["response"]["id"] == "response-123"
    assert trace["model_profile"]["observed"]["model_id"] == "test-model"
    assert trace["confirmed_settings"] is None
    assert trace["request_sha256"]
    assert calls[0]["transport"]["automatic_retries"] == 0
    assert calls[0]["transport"]["follow_redirects"] is False


def test_context_failure_is_final_and_secret_free(series, tmp_path):

    def too_long(**_):

        failure = TransportError(EvaluationErrorType.CONTEXT_ERROR)
        failure.args = ("Authorization: Bearer TOP_SECRET",)
        raise failure

    root = tmp_path / "run"
    report = new_run(config_for(series), root, completion=too_long)
    assert report.details[0].error_type.value == "context_error"
    assert "TOP_SECRET" not in report.model_dump_json()
    assert b"TOP_SECRET" not in (root / "journal.sqlite3").read_bytes()
    resume_run(root, completion=lambda **_: pytest.fail("HTTP"))


def test_explicit_transient_retries_preserve_failed_attempts(series, tmp_path):

    config = config_for(series)
    config.retry.max_attempts = 2
    calls = []

    def retry(**request):
        calls.append(request)
        if len(calls) == 1:
            raise TimeoutError("timed out")
        return answer()

    report = new_run(config, tmp_path / "run", completion=retry)
    assert len(calls) == 9
    assert report.details[0].metadata.request_attempts == 2
    assert report.metrics["token_accounting_complete"] is False
    assert report.runner_provenance["attempts_with_unknown_cost"] == 1


def test_full_and_resumed_report_rebuild_from_same_outcomes(
    series, tmp_path, monkeypatch
):

    original = RunJournal.append
    finalized = []

    def stop_after_commit(self, event):
        original(self, event)
        if event["kind"] == "finalized":
            finalized.append(event)
            if len(finalized) == 3:
                raise KeyboardInterrupt

    root = tmp_path / "run"
    monkeypatch.setattr(RunJournal, "append", stop_after_commit)
    with pytest.raises(KeyboardInterrupt):
        new_run(config_for(series), root, completion=lambda **_: answer())
    monkeypatch.setattr(RunJournal, "append", original)
    report = resume_run(root, completion=lambda **_: answer())
    # A lost/corrupt report snapshot has no authority over committed outcomes.
    (root / "report.json").write_text("torn report")
    rebuilt = resume_run(root, completion=lambda **_: pytest.fail("HTTP"))
    assert rebuilt.metrics == report.metrics
    assert rebuilt.details == report.details
    assert rebuilt.runner_provenance["finalized"] == 8


def test_model_mismatch_stops_run_and_resume(series, tmp_path):

    config = config_for(series)
    config.models[0].expected_profile.served_model_id = "expected-model"
    root = tmp_path / "run"
    calls = []

    def wrong_model(**request):
        calls.append(request)
        return answer()

    with pytest.raises(ValueError, match="profile mismatch"):
        new_run(config, root, completion=wrong_model)
    assert len(calls) == 1
    with pytest.raises(ValueError, match="profile mismatch"):
        resume_run(root, completion=lambda **_: pytest.fail("HTTP"))


def test_response_secrets_are_redacted_and_ids_preserved(series, tmp_path, monkeypatch):

    monkeypatch.setenv("RUNNER_TEST_KEY", "UNIQUE_PRIVATE_CREDENTIAL")
    config = config_for(series)
    config.api_key_env = "RUNNER_TEST_KEY"

    def secret_response(**_):
        raw = answer()
        raw["request_id"] = "request-456"
        raw["headers"] = {"Authorization": "Bearer UNIQUE_PRIVATE_CREDENTIAL"}
        raw["choices"][0]["api_key"] = "UNIQUE_PRIVATE_CREDENTIAL"
        raw["choices"][0]["message"]["content"] = raw["choices"][0]["message"][
            "content"
        ].replace("ok", "UNIQUE_PRIVATE_CREDENTIAL")
        return raw

    root = tmp_path / "run"
    report = new_run(config, root, completion=secret_response)
    assert "UNIQUE_PRIVATE_CREDENTIAL" not in report.model_dump_json()
    assert b"UNIQUE_PRIVATE_CREDENTIAL" not in (root / "journal.sqlite3").read_bytes()
    assert report.details[0].inference["response_id"] == "response-123"
    assert report.details[0].inference["request_id"] == "request-456"


def test_saved_api_failure_replayed_without_http(series, tmp_path, monkeypatch):

    original = RunJournal.append

    def stop_final(self, event):
        if event["kind"] == "finalized":
            raise KeyboardInterrupt
        return original(self, event)

    def unavailable(**_):
        raise TimeoutError("Authorization: Bearer TOP_SECRET")

    root = tmp_path / "run"
    monkeypatch.setattr(RunJournal, "append", stop_final)
    with pytest.raises(KeyboardInterrupt):
        new_run(config_for(series), root, completion=unavailable)
    monkeypatch.setattr(RunJournal, "append", original)
    calls = []

    def rest(**request):
        calls.append(request)
        return answer()

    report = resume_run(root, completion=rest)
    assert len(calls) == 7
    assert report.details[0].error_type.value == "api_timeout"
    assert report.metrics["processed"] == 8


def test_saved_z3_response_survives_execution_interrupt(series, tmp_path, monkeypatch):

    config = config_for(series)
    config.strategies = ["z3"]

    def interrupted(*_):
        raise KeyboardInterrupt

    monkeypatch.setattr(Z3CodeExecutor, "execute", interrupted)
    root = tmp_path / "run"
    raw = answer(json.dumps({"reasoning": "ok", "python_z3_code": "pass"}))
    with pytest.raises(KeyboardInterrupt):
        new_run(config, root, completion=lambda **_: raw)
    timeouts = []

    def execute(executor, _code, _ids):
        timeouts.append(executor.timeout_seconds)
        return Z3ExecutionResult(success=False, error="contract failed")

    monkeypatch.setattr(Z3CodeExecutor, "execute", execute)
    calls = []

    def rest(**request):
        calls.append(request)
        return raw

    report = resume_run(root, completion=rest)
    assert len(calls) == 7
    assert timeouts == [2.0] * 8
    assert all(outcome.error_type.value == "exec_error" for outcome in report.details)
    assert report.metrics["total_tokens_consumed"] == 120


def test_report_provenance_verification_detects_tampering(series, tmp_path):

    root = tmp_path / "run"
    new_run(config_for(series), root, completion=lambda **_: answer())
    verify_runner_report(root / "report.json")
    path = root / "report.json"
    report = json.loads(path.read_text(encoding="utf-8"))
    report["details"][0]["reasoning"] = "replaced"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="provenance"):
        verify_runner_report(path)


def test_selected_unapproved_manifest_cannot_borrow_other_series_gate(series, tmp_path):

    root, manifest = series
    borrowed = manifest.model_copy(deep=True)
    borrowed.ready_for_evaluation = False
    borrowed.failures = ["deliberately unapproved"]
    borrowed.combined_path = str(root / manifest.combined_path)
    for item in borrowed.cells:
        item.dataset_path = str(root / item.dataset_path)
    other = tmp_path / "other"
    other.mkdir()
    path = other / "series.manifest.json"
    path.write_text(borrowed.model_dump_json(), encoding="utf-8")
    config = config_for(series)
    config.series_manifest = str(path)
    with pytest.raises(ValueError, match="not approved"):
        preflight(config)


def test_malformed_http_body_is_saved_finalized_and_replayable(
    series, tmp_path, monkeypatch
):

    report = new_run(
        config_for(series),
        tmp_path / "run",
        completion=lambda **_: {
            "raw_body": "broken JSON",
            "http_status": 200,
            "body_json_error": True,
            "request_id": "wire",
        },
    )
    assert report.details[0].error_type.value == "json_error"
    assert report.details[0].raw_response == "broken JSON"
    assert report.runner_provenance["attempts_with_unknown_cost"] == 8
    monkeypatch.setattr(
        transport, "request_completion", lambda **_: pytest.fail("HTTP")
    )
    resumed = resume_run(tmp_path / "run")
    assert resumed.metrics == report.metrics


def test_observed_profile_fields_are_saved_and_changes_stop_run(series, tmp_path):

    calls = []

    def changed_backend(**request):
        calls.append(request)
        raw = answer()
        raw["model_info"] = {
            "revision": "rev-a" if len(calls) == 1 else "rev-b",
            "quantization": "Q4",
            "context_tokens": 4096,
            "backend_version": "1.0",
            "tokenizer": "declared-tokenizer",
        }
        return raw

    root = tmp_path / "run"
    with pytest.raises(ValueError, match="profile mismatch"):
        new_run(config_for(series), root, completion=changed_backend)
    assert len(calls) == 2
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    observed = report["details"][0]["inference"]["model_profile"]["observed"]
    assert observed["revision"] == "rev-a"
    assert observed["context_tokens"] == 4096
    assert report["details"][1]["error_type"] == "model_profile_mismatch"
