"""Parent-bound evidence and measured input coverage for infrastructure smoke."""

from pathlib import Path

from logicmus_eval.confirmation.evidence_artifacts import (
    _analysis_evidence,
    _artifacts,
    _resume_evidence,
)
from logicmus_eval.confirmation.io import local, read_json
from logicmus_eval.confirmation.models import (
    TRANSPORT_CONTEXT_FAILURES,
    InfrastructureInputAccounting,
    InputTokenMeasurement,
    ReleaseSpec,
    SmokeEvidence,
)
from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.runner.config import RunConfig
from logicmus_eval.runner.preflight import Preflight, digest, preflight
from logicmus_eval.runner.snapshot import VerifiedRun, read_snapshot


def _measurement_max(records: list[InputTokenMeasurement], expected: set[str]) -> int:
    measured = {record.request_sha256: record.input_tokens for record in records}
    if len(measured) != len(records) or measured.keys() != expected:
        raise ValueError("Input accounting must cover every exact request once")
    return max(measured.values())


# The per-model scopes and both exact request sets are deliberately validated together.
# pylint: disable=too-many-locals
def _input_accounting(
    root: Path, evidence: SmokeEvidence, target: Preflight, smoke: Preflight
) -> None:
    accounting = InfrastructureInputAccounting.model_validate(
        read_json(local(root, evidence.longest_input_accounting))
    )
    if (
        accounting.target_requests_sha256 != target.identity["requests_sha256"]
        or accounting.smoke_requests_sha256 != smoke.identity["requests_sha256"]
        or accounting.parent_manifest_sha256 != evidence.parent_manifest_sha256
        or accounting.selection_sha256 != evidence.selection_sha256
    ):
        raise ValueError("Input accounting inventory/parent/selection differs")
    expected = {
        (model.model_id, strategy)
        for model in smoke.config.models
        for strategy in smoke.config.strategies
    }
    observed = [(item.model_id, item.strategy) for item in accounting.measurements]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError("Input accounting model/strategy coverage differs")
    for item in accounting.measurements:
        model = next(m for m in smoke.config.models if m.model_id == item.model_id)
        profile = model.expected_profile
        if (
            item.tokenizer != profile.tokenizer
            or item.chat_template != profile.chat_template
        ):
            raise ValueError("Input accounting tokenizer/chat template differs")
        target_counts = {row.request_sha256: row.input_tokens for row in item.target}
        smoke_counts = {row.request_sha256: row.input_tokens for row in item.smoke}
        if any(
            target_counts[key] != smoke_counts[key]
            for key in target_counts.keys() & smoke_counts.keys()
        ):
            raise ValueError("Input accounting disagrees on identical requests")
        maxima = []
        for records, ready in ((item.target, target), (item.smoke, smoke)):
            hashes = {
                digest(job.request)
                for job in ready.jobs
                if (job.model.model_id, job.strategy) == (item.model_id, item.strategy)
            }
            maxima.append(_measurement_max(records, hashes))
        if maxima[1] < maxima[0]:
            raise ValueError("Longest input token coverage is insufficient")
        if profile.context_tokens is None or (
            max(maxima) + model.generation.max_tokens > profile.context_tokens
        ):
            raise ValueError(
                "Input accounting exceeds verified context or context is unknown"
            )


def _selected_identity(
    snapshot: VerifiedRun, ready: Preflight, evidence: SmokeEvidence
) -> None:
    saved = snapshot.manifest.payload.identity
    selection = saved.smoke_selection
    if (
        evidence.evidence_version != "infrastructure-smoke-v1"
        or saved.runner_protocol != "infrastructure-smoke-v1"
        or saved.config.infrastructure_smoke is None
        or selection is None
    ):
        raise ValueError("Infrastructure smoke parent/selection/run identity differs")
    if (
        selection.parent_manifest_sha256 != evidence.parent_manifest_sha256
        or selection.selection_sha256 != evidence.selection_sha256
        or digest(saved.saved_json()) != ready.identity_hash
        or [job.job_id for job in ready.jobs] != snapshot.manifest.payload.job_ids
    ):
        raise ValueError("Infrastructure smoke parent/selection/run identity differs")
    if len(snapshot.states) != len(ready.jobs) or any(
        not state.attempts or state.outcome is None
        for state in snapshot.states.values()
    ):
        raise ValueError("Infrastructure smoke must retain every planned outcome")


def _infrastructure_artifacts(
    root: Path, config: RunConfig, evidence: SmokeEvidence
) -> None:
    selection = config.infrastructure_smoke
    if selection is None:
        raise ValueError("Infrastructure smoke selection is required")
    paths = [
        Path(config.series_manifest),
        Path(selection.selection_path),
        local(root, evidence.run_dir) / "run.manifest.json",
        local(root, evidence.run_dir) / "journal.sqlite3",
        local(root, evidence.analysis_dir) / "analysis.manifest.json",
    ]
    required = set()
    for path in paths:
        resolved = path.resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ValueError(
                "Infrastructure evidence must contain portable parent/selection artifacts"
            )
        required.add(resolved.relative_to(root.resolve()).as_posix())
    if not required <= evidence.artifacts.keys():
        raise ValueError(
            "Infrastructure evidence must hash parent, selection, journal and analysis"
        )


def _real_http(snapshot: VerifiedRun) -> None:
    for state in snapshot.states.values():
        if not state.attempts or state.outcome is None:
            raise ValueError("Smoke has pending or indeterminate work")
        for attempt in state.attempts:
            result = attempt.result
            if (
                result is None
                or attempt.intent.invocation_origin != "http-adapter"
                or result.kind != "response"
                or result.response.get("http_status") != 200
                or not result.response.get("raw_body")
            ):
                raise ValueError(
                    "Real HTTP-adapter envelope is missing or transport failed; "
                    "mocks are not smoke evidence"
                )
        if state.outcome.error_type is not None and state.outcome.error_type.value in (
            TRANSPORT_CONTEXT_FAILURES
            | {"api_rate_limit", "api_unavailable", "generation_truncated"}
        ):
            raise ValueError(
                "Smoke transport/context/budget failure retained in outcomes"
            )


def check_development_smoke(
    root: Path, config: RunConfig, evidence: SmokeEvidence
) -> None:
    """Verify real infrastructure evidence without admitting a confirmation release."""
    _artifacts(root, evidence.artifacts)
    smoke_root = local(root, evidence.run_dir)
    snapshot = read_snapshot(smoke_root, [smoke_root / "report.json"])
    ready = preflight(config)
    _selected_identity(snapshot, ready, evidence)
    _infrastructure_artifacts(root, config, evidence)
    target_config = config.model_copy(deep=True)
    target_config.infrastructure_smoke = None
    target = preflight(target_config)
    _input_accounting(root, evidence, target, ready)
    _resume_evidence(root, evidence, smoke_root)
    _analysis_evidence(root, evidence, snapshot.manifest.payload.run_id)
    _real_http(snapshot)


# pylint: disable=too-many-locals
def _check_infrastructure_release_smoke(
    root: Path,
    spec: ReleaseSpec,
    config: RunConfig,
    evidence: SmokeEvidence,
    planned: ExperimentPlan,
) -> None:
    from logicmus_eval.infrastructure_smoke import (  # pylint: disable=import-outside-toplevel
        SelectionRule,
    )

    if spec.smoke_selection_rule is None:
        raise ValueError("Infrastructure smoke requires a frozen selection rule")
    rule = SelectionRule.model_validate_json(
        local(root, spec.smoke_selection_rule).read_text(encoding="utf-8")
    )
    _artifacts(root, evidence.artifacts)
    smoke_root = local(root, evidence.run_dir)
    snapshot = read_snapshot(smoke_root, [smoke_root / "report.json"])
    saved = snapshot.manifest.payload.identity
    actual = saved.config.model_dump(mode="json")
    expected = config.model_dump(mode="json")
    for payload in (actual, expected):
        payload.pop("series_manifest")
        payload.pop("infrastructure_smoke", None)
    ready = preflight(saved.config)
    _selected_identity(snapshot, ready, evidence)
    _infrastructure_artifacts(root, saved.config, evidence)
    if (
        actual != expected
        or saved.smoke_selection is None
        or saved.smoke_selection.rule != rule
        or saved.smoke_selection.parent_plan_sha256 != planned.plan_hash
    ):
        raise ValueError("Smoke inference conditions/frozen parent/selection differ")
    _input_accounting(root, evidence, preflight(config), ready)
    _resume_evidence(root, evidence, smoke_root)
    _analysis_evidence(root, evidence, snapshot.manifest.payload.run_id)
    _real_http(snapshot)
