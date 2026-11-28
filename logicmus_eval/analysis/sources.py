"""Historical snapshots and typed compatibility checks; no inference imports."""

from collections import defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from logicmus_eval.analysis.models import (
    AnalysisRow,
    CompatibilityConditions,
    CompatibilityDiagnostic,
    ReportEvidence,
    RunEvidence,
)
from logicmus_eval.models.evaluation import EvaluationSummary
from logicmus_eval.runner.preflight import digest
from logicmus_eval.runner.snapshot import read_snapshot, run_root
from logicmus_eval.runner.snapshot_models import (
    JSON_OBJECT,
    SavedPayload,
    SavedRequest,
    Strategy,
)


@dataclass(frozen=True)
class Snapshot:
    root: Path
    payload: SavedPayload
    report: EvaluationSummary
    requests: dict[str, SavedRequest]
    evidence: RunEvidence


def discover(inputs: list[Path]) -> list[Path]:
    reports: set[Path] = set()
    for supplied in inputs:
        path = supplied.resolve()
        if path.is_file():
            reports.add(path)
        elif (path / "run.manifest.json").is_file():
            reports.add(path / "report.json")
        else:
            found = sorted(path.rglob("run.manifest.json"))
            if not found:
                raise ValueError(f"No saved runner manifests in {path}")
            reports.update(item.parent / "report.json" for item in found)
    if not reports:
        raise ValueError("No input reports")
    return sorted(reports)


def load_snapshots(inputs: list[Path]) -> list[Snapshot]:
    roots: dict[Path, list[Path]] = defaultdict(list)
    for path in discover(inputs):
        roots[run_root(path)].append(path)
    by_run: dict[str, Snapshot] = {}
    for root, supplied in sorted(roots.items()):
        root_report = root / "report.json"
        saved = read_snapshot(root, [root_report, *supplied])
        payload = saved.manifest.payload
        evidence = RunEvidence(
            run_id=payload.run_id,
            root=str(root),
            manifest_sha256=saved.manifest.manifest_sha256,
            identity_sha256=digest(payload.identity.saved_json()),
            journal_head_sha256=saved.journal_head,
            journal_event_count=saved.journal_events,
            files=saved.files,
            supplied_reports=[
                ReportEvidence(
                    path=str(path),
                    sha256=saved.files[path.relative_to(root).as_posix()],
                )
                for path in supplied
            ],
        )
        if previous := by_run.get(payload.run_id):
            prior = previous.evidence
            if (
                prior.manifest_sha256,
                prior.journal_head_sha256,
                prior.journal_event_count,
            ) != (
                evidence.manifest_sha256,
                evidence.journal_head_sha256,
                evidence.journal_event_count,
            ):
                raise ValueError(
                    f"Conflicting snapshots for run_id {payload.run_id}; select one explicitly"
                )
            prior.supplied_reports.extend(evidence.supplied_reports)
        else:
            by_run[payload.run_id] = Snapshot(
                root, payload, saved.reports[root_report], saved.requests, evidence
            )
    return [snapshot for _, snapshot in sorted(by_run.items())]


def conditions(
    snapshot: Snapshot, model_id: str, strategy: Strategy
) -> CompatibilityConditions:
    identity = snapshot.payload.identity
    config = identity.config
    model = next(item for item in config.models if item.model_id == model_id)
    return CompatibilityConditions(
        identity.runner_protocol,
        identity.transport_protocol,
        identity.report_schema_version,
        identity.metric_definitions_version,
        identity.source_bundle_sha256,
        identity.runtime,
        model,
        config.endpoint,
        config.request_timeout_seconds,
        config.retry,
        identity.z3_execution_protocol_version if strategy == "z3" else None,
        config.z3_timeout_seconds if strategy == "z3" else None,
        identity.generation_protocol or "controlled-v1",
    )


CONDITIONS = TypeAdapter(CompatibilityConditions)


def _condition_hash(value: CompatibilityConditions) -> str:
    return digest(CONDITIONS.dump_python(value, mode="json", exclude_none=True))


def _check_request(
    row: AnalysisRow,
    result: CompatibilityDiagnostic,
    requests: dict[tuple[str, Strategy, str], str],
) -> None:
    model, strategy = row.dimensions.model_id, row.dimensions.strategy
    request = row.snapshot.requests[row.job.job_id]
    body = JSON_OBJECT.validate_python(
        request.body.model_dump(mode="json", by_alias=True, exclude_unset=True)
    )
    body.pop("messages")
    signature, schema_key = digest(body), model + "/" + strategy
    if (
        schema_key in result.schema_parameter_hashes
        and result.schema_parameter_hashes[schema_key] != signature
    ):
        raise ValueError(f"Incompatible prompt/schema/parameters for {schema_key}")
    result.schema_parameter_hashes[schema_key] = signature
    request_key, fingerprint = (
        (model, strategy, row.job.case_uid),
        digest(request.saved_json()),
    )
    if request_key in requests and requests[request_key] != fingerprint:
        raise ValueError(f"Incompatible saved prompts for {request_key}")
    requests[request_key] = fingerprint


def check_compatibility(rows: list[AnalysisRow]) -> CompatibilityDiagnostic:
    result = CompatibilityDiagnostic()
    scoped: dict[tuple[str, Strategy], str] = {}
    requests: dict[tuple[str, Strategy, str], str] = {}
    profiles: dict[tuple[str, str], JsonValue] = {}
    for row in rows:
        model, strategy = row.dimensions.model_id, row.dimensions.strategy
        condition = conditions(row.snapshot, model, strategy)
        if row.provenance.protocol_version != condition.generation_protocol:
            raise ValueError("Generation protocol differs from saved run identity")
        if condition.metric_definitions_version != "3":
            raise ValueError(
                "Unsupported historical metric definitions; use legacy mode"
            )
        common = _condition_hash(
            replace(
                condition, z3_execution_protocol_version=None, z3_timeout_seconds=None
            )
        )
        specific = _condition_hash(condition)
        if (
            model in result.common_conditions
            and result.common_conditions[model] != common
        ) or ((model, strategy) in scoped and scoped[model, strategy] != specific):
            raise ValueError(
                f"Incompatible execution/transport/inference conditions for {(model, strategy)}"
            )
        result.common_conditions[model] = common
        scoped[model, strategy] = specific
        _check_request(row, result, requests)
        observed = JSON_OBJECT.validate_python(
            row.trace.model_profile.observed.model_dump(exclude_none=True)
        )
        for name, value in observed.items():
            profile_key = (model, name)
            if profile_key in profiles and profiles[profile_key] != value:
                raise ValueError(f"Incompatible observed model profile {profile_key}")
            profiles[profile_key] = value
    result.strategy_conditions = {str(key): value for key, value in scoped.items()}
    return result
