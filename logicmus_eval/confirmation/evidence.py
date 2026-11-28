"""Validate saved operator/backend and real development smoke evidence offline.

An operator's attestation remains an assertion. Journal/HTTP envelopes support it;
they cannot cryptographically prove which weights a remote server actually used.
"""

from pathlib import Path
from typing import Any

from logicmus_eval.analysis.models import AnalysisManifest, RunEvidence
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


def _artifacts(root: Path, artifacts: dict[str, str]) -> None:
    for name, checksum in artifacts.items():
        if compute_file_sha256(local(root, name)) != checksum:
            raise ValueError(f"Operator evidence hash differs: {name}")


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


def _resume_evidence(root: Path, evidence: SmokeEvidence, snapshot_root: Path) -> None:
    before_path = local(root, evidence.resume_before_report)
    after_path = local(root, evidence.resume_after_report)
    required = {
        evidence.resume_before_report,
        evidence.resume_after_report,
        evidence.longest_input_accounting,
    }
    if not required <= evidence.artifacts.keys():
        raise ValueError("Smoke checkpoints/accounting must have evidence hashes")
    before = read_snapshot(snapshot_root, [before_path]).reports[before_path]
    after = read_snapshot(snapshot_root, [after_path]).reports[after_path]
    # Both are full completed snapshots under the same journal: a no-op resume
    # demonstrates journal compatibility without erasing any failed model answers.
    if before != after or not before.details:
        raise ValueError(
            "No-op resume must preserve the complete report and every outcome"
        )


def _analysis_evidence(root: Path, evidence: SmokeEvidence, run_id: str) -> None:
    analysis = local(root, evidence.analysis_dir)
    manifest = AnalysisManifest.model_validate(
        read_json(analysis / "analysis.manifest.json")
    )
    if manifest.status != "complete":
        raise ValueError("Smoke analysis did not complete")
    plan = manifest.plan
    if (
        plan.purpose != "development"
        or plan.mode != "primary"
        or manifest.plan_sha256 != digest(plan.model_dump(mode="json"))
        or manifest.methods != plan.intervals
        or {r for g in plan.groups for r in g.run_ids} != {run_id}
    ):
        raise ValueError(
            "Smoke analysis must select exactly the development smoke UUID"
        )
    if (
        len(manifest.inputs) != 1
        or not isinstance(manifest.inputs[0], RunEvidence)
        or manifest.inputs[0].run_id != run_id
    ):
        raise ValueError("Smoke analysis input identity differs")
    smoke_root = local(root, evidence.run_dir)
    snapshot = read_snapshot(smoke_root, [smoke_root / "report.json"])
    saved = manifest.inputs[0]
    if (
        saved.manifest_sha256 != snapshot.manifest.manifest_sha256
        or saved.identity_sha256
        != digest(snapshot.manifest.payload.identity.saved_json())
        or saved.journal_head_sha256 != snapshot.journal_head
        or saved.journal_event_count != snapshot.journal_events
        or any(
            saved.files.get(name) != checksum
            for name, checksum in snapshot.files.items()
        )
    ):
        raise ValueError("Smoke analysis provenance differs from verified snapshot")
    if (
        not {"cases.csv", "summary.csv", "contrasts.csv", "diagnostics.json"}
        <= manifest.artifacts.keys()
    ):
        raise ValueError("Smoke analysis artifacts are incomplete")
    for name, checksum in manifest.artifacts.items():
        if compute_file_sha256(local(analysis, name)) != checksum:
            raise ValueError("Smoke analysis artifacts changed")


# A smoke is checked as a whole, with every stored model outcome retained.
# pylint: disable=too-many-locals
def check_smoke(root: Path, spec: ReleaseSpec, configs: dict[str, RunConfig]) -> None:
    supplied = read_json(root / "smoke.evidence.json")
    if supplied.keys() != configs.keys():
        raise ValueError("Real smoke evidence must cover every logical run")
    planned = ExperimentPlan.model_validate_json(
        local(root, spec.smoke_plan).read_text(encoding="utf-8")
    )
    for name, config in configs.items():
        evidence = SmokeEvidence.model_validate(supplied[name])
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
        for state in snapshot.states.values():
            # Successful HTTP transport is distinct from a correct model answer.
            if not state.attempts or state.outcome is None:
                raise ValueError("Smoke has pending or indeterminate work")
            raw = state.outcome.inference
            response = raw.get("response") if isinstance(raw, dict) else None
            if (
                not isinstance(response, dict)
                or response.get("http_status") != 200
                or not response.get("raw_body")
            ):
                raise ValueError(
                    "Real HTTP-adapter envelope is missing; mocks are not smoke evidence"
                )
            if (
                state.outcome.error_type is not None
                and state.outcome.error_type.value
                in {
                    "context_error",
                    "model_profile_mismatch",
                    "api_error",
                    "api_timeout",
                    "api_connection",
                }
            ):
                raise ValueError("Smoke infrastructure failure retained in outcomes")
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
