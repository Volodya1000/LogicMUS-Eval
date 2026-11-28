"""Validate saved operator/backend and real development smoke evidence offline.

An operator's attestation remains an assertion. Journal/HTTP envelopes support it;
they cannot cryptographically prove which weights a remote server actually used.
"""

from pathlib import Path
from typing import Any

from logicmus_eval.confirmation.evidence_artifacts import (
    _analysis_evidence,
    _artifacts,
    _resume_evidence,
)
from logicmus_eval.confirmation.infrastructure_evidence import (
    _check_infrastructure_release_smoke,
    _real_http,
)
from logicmus_eval.confirmation.io import local, read_json
from logicmus_eval.confirmation.models import (
    BackendEvidence,
    ReleaseSpec,
    SmokeEvidence,
)
from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.hashing import compute_file_sha256, compute_source_bundle_hash
from logicmus_eval.runner.config import RunConfig
from logicmus_eval.runner.preflight import digest, preflight
from logicmus_eval.runner.snapshot import read_snapshot


# Calibration and attestation are checked together against the exact planned run.
# pylint: disable=too-many-locals,too-many-branches
def check_backend(root: Path, spec: ReleaseSpec, configs: dict[str, RunConfig]) -> None:
    supplied = read_json(root / "backend.evidence.json")
    if supplied.keys() != configs.keys():
        raise ValueError("Backend evidence must cover every logical run")
    for name, config in configs.items():
        evidence = BackendEvidence.model_validate(supplied[name])
        _artifacts(root, evidence.artifacts)
        if evidence.config_sha256 != compute_file_sha256(
            local(root, spec.configs[name])
        ):
            raise ValueError("Backend verification refers to different configuration")
        ready = preflight(config)
        if evidence.requests_sha256 != ready.identity["requests_sha256"]:
            raise ValueError("Backend context accounting refers to different requests")
        for model in config.models:
            context = model.expected_profile.context_tokens
            if (
                context is None
                or evidence.max_input_tokens + model.generation.max_tokens > context
            ):
                raise ValueError(
                    "Planned longest input plus output cap exceeds verified context"
                )
        calibration_root = local(root, evidence.development_calibration_run)
        calibration = read_snapshot(
            calibration_root, [calibration_root / "report.json"]
        )
        calibration_config = calibration.manifest.payload.identity.config
        calibration_ready = preflight(calibration_config)
        if calibration_config.infrastructure_smoke is not None and (
            calibration.manifest.payload.identity.runner_protocol
            != "infrastructure-smoke-v1"
            or digest(calibration.manifest.payload.identity.saved_json())
            != calibration_ready.identity_hash
        ):
            raise ValueError(
                "Development calibration parent/selection identity differs"
            )
        if (
            calibration.manifest.payload.identity.config.models != config.models
            or any(
                outcome.experiment is None
                or outcome.experiment.purpose != "development"
                for outcome in calibration.reports[
                    calibration_root / "report.json"
                ].details
            )
            or not calibration.states
            or len(calibration.reports[calibration_root / "report.json"].details)
            != len(calibration.states)
            or any(
                not state.attempts or state.outcome is None
                for state in calibration.states.values()
            )
        ):
            raise ValueError(
                "Budget/timeout calibration must use development tasks and identical models"
            )
        if (
            calibration.manifest.payload.identity.config.request_timeout_seconds
            != config.request_timeout_seconds
        ):
            raise ValueError("Timeout differs from development calibration")
        for state in calibration.states.values():
            if (
                state.outcome is not None
                and state.outcome.error_type is not None
                and state.outcome.error_type.value
                in {
                    "generation_truncated",
                    "api_timeout",
                    "context_error",
                    "model_profile_mismatch",
                }
            ):
                raise ValueError(
                    "Development calibration has truncation/timeout/profile/context failure"
                )
            for attempt in state.attempts:
                result = attempt.result
                if (
                    result is None
                    or result.kind == "indeterminate_retry"
                    or (
                        result.kind == "request_error"
                        and result.error_type == "api_timeout"
                    )
                ):
                    raise ValueError(
                        "Development calibration has unknown or timed-out attempts"
                    )
        _real_http(calibration)


# A smoke is checked as a whole, with every stored model outcome retained.
# pylint: disable=too-many-locals,too-many-branches
def check_smoke(root: Path, spec: ReleaseSpec, configs: dict[str, RunConfig]) -> None:
    supplied = read_json(root / "smoke.evidence.json")
    if supplied.keys() != configs.keys():
        raise ValueError("Real smoke evidence must cover every logical run")
    planned = ExperimentPlan.model_validate_json(
        local(root, spec.smoke_plan).read_text(encoding="utf-8")
    )
    for name, config in configs.items():
        evidence = SmokeEvidence.model_validate(supplied[name])
        if evidence.evidence_version == "infrastructure-smoke-v1":
            _check_infrastructure_release_smoke(root, spec, config, evidence, planned)
            continue
        if spec.smoke_selection_rule is not None:
            raise ValueError("Frozen infrastructure smoke cannot use legacy evidence")
        _artifacts(root, evidence.artifacts)
        smoke_root = local(root, evidence.run_dir)
        snapshot = read_snapshot(smoke_root, [smoke_root / "report.json"])
        saved = snapshot.manifest.payload.identity
        observed_config = saved.config
        # Only dataset purpose/selection changes for the development smoke.
        expected = config.model_dump(mode="json")
        actual = observed_config.model_dump(mode="json")
        expected.pop("series_manifest")
        actual.pop("series_manifest")
        if (
            actual != expected
            or saved.source_bundle_sha256 != compute_source_bundle_hash()
        ):
            raise ValueError(
                "Smoke model/strategy/generation/backend/source conditions differ"
            )
        smoke_ready = preflight(observed_config)
        smoke_manifest = read_json(Path(observed_config.series_manifest))
        if smoke_manifest["plan_sha256"] != planned.plan_hash:
            raise ValueError("Smoke did not use the frozen development plan")
        if len(snapshot.reports[smoke_root / "report.json"].details) != len(
            smoke_ready.jobs
        ):
            raise ValueError("Smoke must retain every planned outcome")
        domains = {
            (j.case.metadata["pattern_id"] == "math", j.case.is_satisfiable, j.strategy)
            for j in smoke_ready.jobs
        }
        expected_domains = {
            (numeric, sat, strategy)
            for numeric in (False, True)
            for sat in (False, True)
            for strategy in config.strategies
        }
        if not expected_domains <= domains:
            raise ValueError(
                "Smoke must include Boolean/numeric SAT/UNSAT and both strategies"
            )
        # Wrong model reasoning remains an outcome; origin/transport/budget are separate.
        _real_http(snapshot)
        accounting: dict[str, Any] = read_json(
            local(root, evidence.longest_input_accounting)
        )
        ready = preflight(config)
        if (
            accounting["confirmation_requests_sha256"]
            != ready.identity["requests_sha256"]
            or accounting["smoke_requests_sha256"]
            != smoke_ready.identity["requests_sha256"]
            or accounting["smoke_max_input_tokens"]
            < accounting["confirmation_max_input_tokens"]
            or accounting["confirmation_max_input_tokens"] <= 0
        ):
            raise ValueError(
                "Longest planned input was not covered by development token accounting"
            )
        _resume_evidence(root, evidence, smoke_root)
        _analysis_evidence(root, evidence, snapshot.manifest.payload.run_id)
