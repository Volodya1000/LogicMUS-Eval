"""Offline inventory and identity. No client import, endpoint access or generation."""

import hashlib
import platform
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any

from logicmus_eval.evaluation.strategies import (
    DirectEvaluationStrategy,
    Z3TranslationEvaluationStrategy,
)
from logicmus_eval.experiment_plan import canonical_json, content_id
from logicmus_eval.hashing import compute_file_sha256, compute_source_bundle_hash
from logicmus_eval.infrastructure_smoke import load_admitted_cases, validate_selection
from logicmus_eval.models.evaluation import (
    METRIC_DEFINITIONS_VERSION,
    REPORT_SCHEMA_VERSION,
    Z3_EXECUTION_PROTOCOL_VERSION,
)
from logicmus_eval.models.llm import DirectReasoningResponse, LLMToZ3Response
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.runner.config import ModelConfig, RunConfig
from logicmus_eval.runner.requests import build_request

# Preserve the historical module exports while serialization lives independently.
__all__ = [
    "DirectEvaluationStrategy",
    "DirectReasoningResponse",
    "Job",
    "LLMToZ3Response",
    "Preflight",
    "Z3TranslationEvaluationStrategy",
    "build_request",
    "digest",
    "preflight",
]


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


def preflight(config: RunConfig) -> Preflight:  # pylint: disable=too-many-locals
    config = RunConfig.model_validate(config.model_dump())
    path = Path(config.series_manifest).resolve()
    if path.name != "series.manifest.json":
        raise ValueError("Expected series.manifest.json")
    plan, cases = load_admitted_cases(path)
    selection = None
    if config.infrastructure_smoke is not None:
        selection_path = Path(config.infrastructure_smoke.selection_path).resolve()
        config.infrastructure_smoke.selection_path = str(selection_path)
        selection = validate_selection(path, selection_path, cases, config=config)
        if selection.selection_sha256 != config.infrastructure_smoke.selection_sha256:
            raise ValueError("Smoke selection hash differs from pinned configuration")
        selected_ids = set(selection.case_uids)
        cases = [case for case in cases if case.case_id in selected_ids]
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
    identity["generation_protocol"] = plan.protocol_version
    if selection is not None:
        identity["runner_protocol"] = "infrastructure-smoke-v1"
        identity["smoke_selection"] = selection.model_dump(mode="json")
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
