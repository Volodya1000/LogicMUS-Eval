"""Numerical regressions use the real extractor/strategies with an offline API."""

import json
from pathlib import Path
from types import SimpleNamespace

import litellm
import pytest
from tenacity import wait_none

from logicmus_eval.evaluate_llm import _build_metrics, run_evaluation
from logicmus_eval.evaluation.pipeline import EvaluationPipeline
from logicmus_eval.evaluation.strategies import (
    DirectEvaluationStrategy,
    Z3TranslationEvaluationStrategy,
)
from logicmus_eval.extractor import ExtractorError, StructuredOutputExtractor
from logicmus_eval.models.evaluation import (
    CasePrediction,
    EvaluationSummary,
    ExtractionMetadata,
    Z3ExecutionResult,
)
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.sandbox.executor import SAFE_BUILTINS, Z3CodeExecutor


def case(index=0, *, sat=True, core=()):
    return LogicTestCase(
        case_id=f"c{index}",
        mus_size=2,
        is_satisfiable=sat,
        template_pack_id="pack_00",
        predicate_mapping={},
        rules=[
            {"id": f"R{i}", "text": f"Rule {i}", "operator_type": "FACT"}
            for i in range(1, 5)
        ],
        mus_expected=list(core),
    )


def response(content, *, usage=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=usage,
    )


def answer(sat=True, core=(), reasoning="analysis"):
    return response(
        json.dumps(
            {
                "reasoning": reasoning,
                "is_sat": sat,
                "conflict_core": list(core),
            }
        )
    )


def offline_pipeline(monkeypatch, outcomes, *, strategy=None):
    outcomes = iter(outcomes)

    def complete(**_kwargs):
        outcome = next(outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    monkeypatch.setattr("logicmus_eval.extractor.litellm.completion", complete)
    # Patch tenacity's wait policy, preserving the real retry loop.
    monkeypatch.setattr(
        "logicmus_eval.extractor.wait_exponential", lambda **_kw: wait_none()
    )
    return EvaluationPipeline(
        strategy or DirectEvaluationStrategy(),
        StructuredOutputExtractor("offline"),
        _build_metrics(),
    )


def test_twenty_cases_errors_stay_in_denominator(monkeypatch):
    outcomes = [answer()] * 16 + [answer(False)] + [response("broken")] * 3
    report = offline_pipeline(monkeypatch, outcomes).run([case(i) for i in range(20)])
    assert report.metrics["sat_accuracy"] == pytest.approx(0.8)
    assert report.metrics["valid_response_accuracy"] == pytest.approx(16 / 17)
    assert report.metrics["coverage"] == pytest.approx(17 / 20)
    assert (
        report.metrics["processed"]
        == len(report.details)
        == report.metrics["planned"]
        == 20
    )
    assert (
        report.metrics["correct_sat"]
        == sum(d.is_sat_correct for d in report.details)
        == 16
    )
    assert (
        report.metrics["valid_responses_evaluated"]
        == sum(d.valid_response for d in report.details)
        == 17
    )
    assert report.status == "completed"


@pytest.mark.parametrize(
    "kind",
    [
        "json_error",
        "schema_error",
        "api_timeout",
        "api_connection",
        "api_rate_limit",
        "empty_response",
        "extraction_error",
    ],
)
def test_expected_errors_continue_and_keep_stage(monkeypatch, kind):
    errors = {
        "json_error": [response("broken")],
        "schema_error": [response('{"is_sat": true}')],
        "empty_response": [response("")],
        "extraction_error": [ExtractorError("failed extraction")],
        "api_timeout": [litellm.exceptions.Timeout("timeout", "offline", "openai")] * 3,
        "api_connection": [
            litellm.exceptions.APIConnectionError("connection", "offline", "openai")
        ]
        * 3,
        "api_rate_limit": [
            litellm.exceptions.RateLimitError("limit", "openai", "offline")
        ]
        * 3,
    }
    pipeline = offline_pipeline(monkeypatch, errors[kind] + [answer()])
    report = pipeline.run([case(), case(1)])
    failed, success = report.details
    assert failed.error_type == kind
    assert failed.error_stage in {
        "request",
        "parse",
        "schema",
        "extraction",
        "response",
    }
    assert failed.error and kind in failed.failure_tags
    assert "exec_error" not in failed.failure_tags
    assert failed.valid_response is False
    assert success.is_sat_correct
    assert report.metrics["sat_accuracy"] == 0.5
    assert report.metrics["processed"] == 2
    assert report.metrics["error_count"] == 1
    assert report.metrics["error_counts"] == {kind: 1}


def test_sat_with_correct_core_is_invalid_and_earns_no_credit(monkeypatch):
    report = offline_pipeline(monkeypatch, [answer(True, ["R1", "R2"])]).run(
        [case(sat=False, core=["R1", "R2"])]
    )
    assert report.metrics["mus_exact_match"] == report.metrics["mus_f1"] == 0
    assert not report.details[0].valid_response
    assert report.details[0].predicted_sat is True
    assert report.details[0].predicted_mus == ["R1", "R2"]
    assert "invalid_response" in report.details[0].failure_tags


def test_macro_f1_averages_unrounded_case_scores(monkeypatch):
    report = offline_pipeline(
        monkeypatch,
        [
            answer(False, ["R1"]),
            answer(False, ["R1", "R2"]),
            response("broken"),
        ],
    ).run(
        [
            case(0, sat=False, core=["R1", "R2"]),
            case(1, sat=False, core=["R1"]),
            case(2, sat=False, core=["R1"]),
        ]
    )
    assert report.metrics["unsat_evaluated"] == 3
    assert report.metrics["mus_precision"] == pytest.approx(1 / 2)
    assert report.metrics["mus_recall"] == pytest.approx(1 / 2)
    assert report.metrics["mus_f1"] == pytest.approx(4 / 9)
    assert [d.mus_f1 for d in report.details] == pytest.approx([2 / 3, 2 / 3, 0])
    assert [d.valid_response for d in report.details] == [True, True, False]


def test_empty_subset_and_all_sat_return_null_for_missing_denominators(
    monkeypatch, tmp_path
):
    pipeline = offline_pipeline(monkeypatch, [answer()])
    path = tmp_path / "empty.json"
    empty = pipeline.run([case()], limit=0, output_path=path)
    assert empty.metrics["processed"] == empty.metrics["planned"] == 0
    for key in (
        "sat_accuracy",
        "valid_response_accuracy",
        "coverage",
        "mus_exact_match",
        "mus_precision",
        "mus_recall",
        "mus_f1",
    ):
        assert empty.metrics[key] is None
    assert json.loads(path.read_text())["status"] == "completed"
    sat = pipeline.run([case()])
    assert sat.metrics["unsat_evaluated"] == 0
    assert sat.metrics["mus_f1"] is None


def test_all_unsuccessful_refusal_and_missing_verdict(monkeypatch):
    report = offline_pipeline(
        monkeypatch,
        [
            answer(False, ["R1"], "no explicit initial"),
            response("broken"),
            response('{"reasoning":"analysis","is_sat":null,"conflict_core":[]}'),
        ],
    ).run([case(i, sat=False, core=["R1"]) for i in range(3)])
    assert report.metrics["sat_accuracy"] == report.metrics["coverage"] == 0
    assert report.metrics["valid_response_accuracy"] is None
    assert report.metrics["mus_f1"] == 0
    assert report.metrics["refusal_count"] == 1
    assert not any(d.is_sat_correct or d.valid_response for d in report.details)


def test_unknown_ids_invalid_duplicates_normalized_and_raw_preserved(monkeypatch):
    duplicate = answer(False, ["R1", "R1"])
    report = offline_pipeline(monkeypatch, [answer(False, ["unknown"]), duplicate]).run(
        [case(i, sat=False, core=["R1"]) for i in range(2)]
    )
    unknown, repeated = report.details
    assert not unknown.valid_response
    assert unknown.error_stage == "response_validation"
    assert "unknown" in unknown.error
    assert repeated.valid_response and repeated.is_mus_correct
    assert repeated.predicted_mus == ["R1"]
    assert repeated.raw_response == duplicate.choices[0].message.content
    assert report.metrics["mus_exact_match"] == 0.5
    assert report.metrics["sat_accuracy"] == 0.5


def test_reusing_pipeline_resets_all_counts(monkeypatch):
    pipeline = offline_pipeline(monkeypatch, [response("broken"), answer()])
    pipeline.run([case()])
    report = pipeline.run([case()])
    assert report.metrics["processed"] == len(report.details) == 1
    assert report.metrics["error_count"] == 0
    assert report.metrics["sat_accuracy"] == report.metrics["coverage"] == 1


def test_bad_json_keeps_known_usage_latency_and_unknowns(monkeypatch):
    known = response(
        "broken",
        usage=SimpleNamespace(
            prompt_tokens=11,
            completion_tokens=7,
            total_tokens=18,
            completion_tokens_details={"reasoning_tokens": 3},
        ),
    )
    pipeline = offline_pipeline(monkeypatch, [known, response("broken")])
    ticks = iter([10.0, 12.0, 20.0, 23.0])
    monkeypatch.setattr(
        "logicmus_eval.extractor.time.perf_counter", lambda: next(ticks)
    )
    report = pipeline.run([case(), case(1)])
    first, second = report.details
    assert first.raw_response == "broken"
    assert first.metadata.total_tokens == 18
    assert first.metadata.latency_seconds == 2
    assert second.metadata.total_tokens is None
    assert second.metadata.latency_seconds == 3
    assert report.metrics["total_tokens_consumed"] == 18
    assert report.metrics["usage_known_cases"]["total_tokens"] == 1
    assert report.metrics["usage_coverage"]["total_tokens"] == 0.5
    assert report.metrics["avg_prompt_tokens"] == 11
    assert report.metrics["total_execution_seconds"] == 5


@pytest.mark.parametrize(
    "error",
    [RuntimeError("bug"), ValueError("config"), KeyboardInterrupt(), SystemExit(2)],
)
def test_unexpected_errors_and_interrupts_propagate_with_partial_report(
    monkeypatch, tmp_path, error
):
    pipeline = offline_pipeline(monkeypatch, [answer(), error])
    path = tmp_path / "partial.json"
    with pytest.raises(type(error)):
        pipeline.run([case(), case(1)], output_path=path)
    partial = EvaluationSummary.model_validate_json(path.read_text())
    assert partial.status == "running"
    assert partial.metrics["processed"] == len(partial.details) == 1
    assert partial.metrics["planned"] == 2


def test_legacy_read_does_not_assign_new_semantics(monkeypatch):
    legacy = EvaluationSummary.model_validate(
        {
            "metrics": {"sat_accuracy": 0.99},
            "details": [
                {
                    "case_id": "old",
                    "mus_size": 2,
                    "expected_sat": True,
                    "predicted_sat": True,
                    "is_sat_correct": True,
                    "expected_mus": [],
                    "predicted_mus": [],
                    "is_mus_correct": False,
                    "metadata": {
                        "prompt_tokens": 0,
                        "completion_tokens": 0,
                        "thinking_tokens": 0,
                        "total_tokens": 0,
                        "latency_seconds": 0.0,
                    },
                    "reasoning": "no explicit initial",
                    "error": "old failure",
                    "failure_tags": ["exec_error"],
                }
            ],
        }
    )
    assert legacy.metric_definitions_version is None
    assert legacy.report_schema_version is None
    assert legacy.status is None
    assert legacy.metrics["sat_accuracy"] == 0.99
    assert legacy.details[0].is_sat_correct is True
    assert legacy.details[0].valid_response is None
    assert legacy.details[0].metadata.total_tokens == 0
    assert legacy.details[0].failure_tags == ["exec_error"]
    new = offline_pipeline(monkeypatch, []).run([])
    assert new.metric_definitions_version == "2"
    assert new.report_schema_version == 2


def test_missing_verdict_from_strategy_is_a_processed_failure(monkeypatch):
    strategy = SimpleNamespace(
        evaluate_case=lambda *_args: (
            CasePrediction(is_sat=None, conflict_core=["R1"], reasoning="partial"),
            ExtractionMetadata(),
        )
    )
    report = offline_pipeline(monkeypatch, [], strategy=strategy).run(
        [case(sat=False, core=["R1"])]
    )
    detail = report.details[0]
    assert detail.predicted_sat is None and detail.predicted_mus == ["R1"]
    assert detail.error_type == "missing_answer" and not detail.valid_response
    assert report.metrics["processed"] == report.metrics["unsat_evaluated"] == 1
    assert report.metrics["sat_accuracy"] == report.metrics["mus_f1"] == 0


def test_execution_failure_retains_prediction_but_earns_zero(monkeypatch):
    executor = SimpleNamespace(
        execute=lambda _code: Z3ExecutionResult(
            success=False, is_sat=False, conflict_core=["R1"], error="execution failed"
        )
    )
    strategy = Z3TranslationEvaluationStrategy(executor=executor)
    report = offline_pipeline(
        monkeypatch,
        [
            response(
                json.dumps(
                    {
                        "reasoning": "analysis",
                        "python_z3_code": "bad code",
                    }
                )
            )
        ],
        strategy=strategy,
    ).run([case(sat=False, core=["R1"])])
    detail = report.details[0]
    assert detail.predicted_sat is False and detail.predicted_mus == ["R1"]
    assert not detail.is_sat_correct and not detail.is_mus_correct
    assert detail.error_type == "exec_error" and detail.error_stage == "execution"
    assert report.metrics["sat_accuracy"] == report.metrics["mus_f1"] == 0


def test_entrypoint_writes_versioned_report_with_run_info(monkeypatch, tmp_path):
    (tmp_path / "external.jsonl").write_text(case().model_dump_json() + "\n")
    offline_pipeline(monkeypatch, [answer()])
    run_evaluation(str(tmp_path), "offline", "direct", 1, "report.json")
    report = EvaluationSummary.model_validate_json(
        (tmp_path / "report.json").read_text()
    )
    assert report.status == "completed" and report.metric_definitions_version == "2"
    assert report.run_info.total_cases_processed == report.metrics["processed"] == 1
    assert report.run_info.finished_at is not None


def test_entrypoint_serializes_initial_and_final_report_once(monkeypatch, tmp_path):
    (tmp_path / "external.jsonl").write_text(
        "\n".join(case(i).model_dump_json() for i in range(3)) + "\n"
    )
    offline_pipeline(monkeypatch, [answer()] * 3)
    snapshots = []

    def capture_write(path, data, **kwargs):
        if path.name == "report.json":
            content = json.loads(data)
            snapshots.append((content["status"], len(content["details"])))
        with path.open("w", **kwargs) as output:
            return output.write(data)

    monkeypatch.setattr(Path, "write_text", capture_write)
    run_evaluation(str(tmp_path), "offline", "direct", 3, "report.json")
    assert snapshots == [("running", 0), ("completed", 3)]


def test_recovered_retry_counts_one_case_and_marks_cost_incomplete(monkeypatch):
    recovered = answer()
    recovered.usage = {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}
    report = offline_pipeline(
        monkeypatch,
        [
            litellm.exceptions.Timeout("timeout", "offline", "openai"),
            recovered,
        ],
    ).run([case()])
    assert report.metrics["processed"] == len(report.details) == 1
    assert report.metrics["error_count"] == 0
    assert report.metrics["sat_accuracy"] == 1
    assert report.metrics["total_tokens_consumed"] == 6
    assert report.details[0].metadata.request_attempts == 2
    assert report.metrics["usage_coverage"]["total_tokens"] == 1
    assert report.metrics["token_accounting_complete"] is False


def test_unknown_usage_is_not_zero_but_reported_zero_is_known(monkeypatch):
    zero = answer()
    zero.usage = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "completion_tokens_details": {"reasoning_tokens": 0},
    }
    pipeline = offline_pipeline(monkeypatch, [answer(), zero])
    unknown = pipeline.run([case()])
    assert unknown.metrics["total_tokens_consumed"] is None
    assert unknown.metrics["avg_prompt_tokens"] is None
    assert unknown.metrics["usage_known_cases"]["total_tokens"] == 0
    reported = pipeline.run([case()])
    assert reported.metrics["total_tokens_consumed"] == 0
    assert reported.metrics["avg_prompt_tokens"] == 0
    assert reported.metrics["token_accounting_complete"] is True


def test_refusal_in_broken_response_is_counted_once_per_category(monkeypatch):
    report = offline_pipeline(
        monkeypatch, [response("no explicit initial; broken JSON")]
    ).run([case()])
    assert report.metrics["processed"] == report.metrics["refusal_count"] == 1
    assert report.metrics["error_count"] == report.metrics["infra_error_count"] == 1
    assert report.metrics["error_counts"] == {"json_error": 1}
    assert set(report.details[0].failure_tags) == {"json_error", "refusal_no_facts"}


def test_provider_refusal_field_is_preserved_and_classified(monkeypatch):
    refused = response(None)
    refused.choices[0].message.refusal = "I cannot help with this request"
    report = offline_pipeline(monkeypatch, [refused, answer()]).run([case(), case(1)])
    assert report.metrics["refusal_count"] == 1
    assert report.metrics["error_count"] == 0
    assert report.metrics["sat_accuracy"] == report.metrics["coverage"] == 0.5
    assert report.details[0].raw_response == "I cannot help with this request"
    assert report.details[0].failure_tags == ["refusal_no_facts"]


def test_interrupted_entrypoint_keeps_run_info_without_finish_time(
    monkeypatch, tmp_path
):
    (tmp_path / "external.jsonl").write_text(
        case().model_dump_json() + "\n" + case(1).model_dump_json() + "\n"
    )
    offline_pipeline(monkeypatch, [answer(), KeyboardInterrupt()])
    with pytest.raises(KeyboardInterrupt):
        run_evaluation(str(tmp_path), "offline", "direct", 2, "report.json")
    report = EvaluationSummary.model_validate_json(
        (tmp_path / "report.json").read_text()
    )
    assert report.status == "running"
    assert report.run_info.finished_at is None
    assert report.run_info.total_cases_processed == report.metrics["processed"] == 1


@pytest.mark.parametrize("error", [KeyboardInterrupt, SystemExit])
def test_generated_process_interrupt_is_not_a_model_failure(monkeypatch, error):
    monkeypatch.setitem(SAFE_BUILTINS, error.__name__, error)
    with pytest.raises(error):
        Z3CodeExecutor().execute(f"raise {error.__name__}()")
