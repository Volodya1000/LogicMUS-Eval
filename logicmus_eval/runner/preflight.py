"""Offline inventory and identity. No client import, endpoint access or generation."""

import hashlib
import json
import platform
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

from logicmus_eval.evaluation.strategies import (
    DirectEvaluationStrategy,
    Z3TranslationEvaluationStrategy,
)
from logicmus_eval.experiment_plan import ExperimentPlan, canonical_json, content_id
from logicmus_eval.hashing import compute_file_sha256, compute_source_bundle_hash
from logicmus_eval.models.evaluation import (
    METRIC_DEFINITIONS_VERSION,
    REPORT_SCHEMA_VERSION,
    Z3_EXECUTION_PROTOCOL_VERSION,
    ExperimentProvenance,
)
from logicmus_eval.models.llm import DirectReasoningResponse, LLMToZ3Response
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.release import assert_controlled_series_approved
from logicmus_eval.runner.config import ModelConfig, RunConfig


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Job:
    job_id: str
    case: LogicTestCase
    model: ModelConfig
    strategy: str
    request: dict[str, Any]


@dataclass
class Preflight:
    config: RunConfig
    identity: dict[str, Any]
    jobs: list[Job]
    counts: dict[str, int]
    unknowns: list[str]

    @property
    def identity_hash(self) -> str:
        return digest(self.identity)


def build_request(
    config: RunConfig, model: ModelConfig, strategy: str, case: LogicTestCase
) -> dict[str, Any]:
    evaluator = (
        DirectEvaluationStrategy()
        if strategy == "direct"
        else Z3TranslationEvaluationStrategy()
    )
    schema = DirectReasoningResponse if strategy == "direct" else LLMToZ3Response
    return {
        "url": config.endpoint.rstrip("/") + "/chat/completions",
        "body": {
            "model": model.model_id,
            "messages": [{"role": "user", "content": evaluator.build_prompt(case)}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                },
            },
            **model.generation.model_dump(exclude_none=True),
            "stream": False,
        },
        "timeout": config.request_timeout_seconds,
        "transport": {
            "automatic_retries": 0,
            "follow_redirects": False,
            "environment_proxies": False,
        },
    }


def preflight(config: RunConfig) -> Preflight:  # pylint: disable=too-many-locals
    config = RunConfig.model_validate(config.model_dump())
    path = Path(config.series_manifest).resolve()
    if path.name != "series.manifest.json":
        raise ValueError("Expected series.manifest.json")
    manifest = assert_controlled_series_approved(path)
    plan = ExperimentPlan.model_validate(manifest.plan)
    combined_path = path.parent / str(manifest.combined_path)
    cases: list[LogicTestCase] = []
    for item in manifest.cells:
        dataset = path.parent / str(item.dataset_path)
        rows = [
            LogicTestCase.model_validate_json(line)
            for line in dataset.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        expected = {record["case_id"] for record in item.smt_checks}
        if len(rows) != len(expected) or {row.case_id for row in rows} != expected:
            raise ValueError("Dataset cases differ from admitted cell evidence")
        for row in rows:
            provenance = ExperimentProvenance.model_validate(row.metadata)
            if (
                provenance.case_uid != row.case_id
                or provenance.cell_id != item.cell.cell_id
                or provenance.total_rules != item.cell.n
                or row.mus_size != item.cell.k
            ):
                raise ValueError("Dataset case provenance differs from plan")
        cases.extend(rows)
    combined = [
        json.loads(line)
        for line in combined_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if combined != [case.model_dump(mode="json") for case in cases]:
        raise ValueError("Combined dataset differs from planned cell contents")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Duplicate case_uid")
    payload = config.model_dump(mode="json")
    payload["series_manifest"] = str(path)
    identity = {
        "runner_protocol": "controlled-run-v1",
        "transport_protocol": "openai-compatible-urllib-v1",
        "config": payload,
        "series_manifest_sha256": compute_file_sha256(path),
        "plan_sha256": plan.plan_hash,
        "source_bundle_sha256": compute_source_bundle_hash(),
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "metric_definitions_version": METRIC_DEFINITIONS_VERSION,
        "z3_execution_protocol_version": Z3_EXECUTION_PROTOCOL_VERSION,
        "runtime": {
            "python": platform.python_version(),
            **{name: version(name) for name in ("pydantic", "z3-solver")},
        },
    }
    requests = [
        (case, model, strategy, build_request(config, model, strategy, case))
        for model in config.models
        for strategy in config.strategies
        for case in cases
    ]
    identity["requests_sha256"] = digest([request for _, _, _, request in requests])
    run_hash = digest(identity)
    jobs = [
        Job(
            content_id(run_hash, case.case_id, model.model_id, strategy),
            case,
            model,
            strategy,
            request,
        )
        for case, model, strategy, request in requests
    ]
    counts: dict[str, int] = {}
    for job in jobs:
        key = f"{job.model.model_id}/{job.strategy}/{job.case.metadata['cell_id']}"
        counts[key] = counts.get(key, 0) + 1
    unknowns = []
    for model in config.models:
        for key, value in model.expected_profile.model_dump().items():
            unknowns.append(
                f"{model.model_id}: {key}: "
                + (
                    "unknown"
                    if value is None
                    else "user_supplied; not server-confirmed"
                )
            )
    unknowns.extend(
        [
            (
                "Input token count/context fit unknown: no trusted tokenizer is configured; "
                "input is never truncated."
            ),
            (
                "Requested generation settings are unconfirmed unless explicitly observed; "
                "acceptance is not confirmation."
            ),
            "Offline preflight does not verify a loaded model or contact the endpoint.",
        ]
    )
    return Preflight(config, identity, jobs, counts, unknowns)
