"""One locked, read-only snapshot for verification, parsing and evidence hashes."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from logicmus_eval.enums import EvaluationStatus
from logicmus_eval.evaluation.metrics import aggregate_outcomes
from logicmus_eval.experiment_plan import content_id
from logicmus_eval.models.evaluation import EvaluationSummary
from logicmus_eval.runner.journal import RunJournal
from logicmus_eval.runner.preflight import digest
from logicmus_eval.runner.snapshot_models import (
    JOURNAL_EVENTS,
    RunnerProvenance,
    SavedManifest,
    SavedRequest,
)
from logicmus_eval.runner.state import SavedState, replay_inventory


@dataclass(frozen=True)
class VerifiedRun:
    manifest: SavedManifest
    reports: dict[Path, EvaluationSummary]
    requests: dict[str, SavedRequest]
    states: dict[str, SavedState]
    files: dict[str, str]
    journal_head: str
    journal_events: int


def run_root(path: Path) -> Path:
    root = next(
        (
            p
            for p in (path.parent, path.parent.parent)
            if (p / "run.manifest.json").is_file()
        ),
        None,
    )
    if root is None:
        raise ValueError(
            "Runner provenance is unavailable; historical reports are not upgraded"
        )
    return root.resolve()


def _inventory(manifest: SavedManifest) -> None:
    payload = manifest.payload
    if manifest.manifest_sha256 != digest(payload.saved_json()):
        raise ValueError("Runner provenance differs from manifest")
    identity_hash = digest(payload.identity.saved_json())
    if payload.job_ids != [job.job_id for job in payload.jobs] or any(
        job.job_id
        != content_id(identity_hash, job.case_uid, job.model_id, job.strategy)
        for job in payload.jobs
    ):
        raise ValueError("Runner inventory differs from saved identity")


def _verify_report(
    report: EvaluationSummary,
    manifest: SavedManifest,
    journal: RunJournal,
    states: dict[str, SavedState],
) -> None:
    provenance = RunnerProvenance.model_validate(report.runner_provenance)
    payload, identity = manifest.payload, manifest.payload.identity
    if (
        provenance.manifest_sha256 != manifest.manifest_sha256
        or provenance.run_id != payload.run_id
        or provenance.identity_sha256 != digest(identity.saved_json())
        or provenance.source_bundle_sha256 != identity.source_bundle_sha256
    ):
        raise ValueError("Runner provenance differs from manifest")
    has_z3 = (
        provenance.strategy == "z3"
        if provenance.strategy
        else "z3" in identity.config.strategies
    )
    if (
        report.report_schema_version != identity.report_schema_version
        or report.metric_definitions_version != identity.metric_definitions_version
        or report.z3_execution_protocol_version
        != (identity.z3_execution_protocol_version if has_z3 else None)
        or provenance.protocol != identity.runner_protocol
    ):
        raise ValueError(
            "Runner report versions differ from saved identity/strategy scope"
        )
    if (
        provenance.journal_head_sha256 != journal.head
        or provenance.journal_event_count != len(journal.events)
    ):
        raise ValueError(
            "Runner provenance differs from journal head; rebuild stale report"
        )
    selected = [
        job
        for job in payload.jobs
        if (provenance.model_id is None or job.model_id == provenance.model_id)
        and (provenance.strategy is None or job.strategy == provenance.strategy)
    ]
    outcomes = [
        state.outcome
        for job in selected
        if (state := states[job.job_id]).outcome is not None
    ]
    metrics = aggregate_outcomes(outcomes, len(selected))
    status = (
        EvaluationStatus.COMPLETED
        if len(outcomes) == len(selected)
        else EvaluationStatus.RUNNING
    )
    if (
        report.details != outcomes
        or report.metrics != metrics
        or report.status != status
    ):
        raise ValueError(
            "Runner report provenance does not match committed outcomes/metrics"
        )


def _read_report(
    path: Path,
    manifest: SavedManifest,
    journal: RunJournal,
    states: dict[str, SavedState],
) -> tuple[EvaluationSummary, bytes]:
    raw = path.read_bytes()
    report = EvaluationSummary.model_validate_json(raw)
    _verify_report(report, manifest, journal, states)
    return report, raw


def read_snapshot(root: Path, paths: list[Path]) -> VerifiedRun:
    """Initial manifest only locates journal identity; all trusted bytes are reread
    and hashed under the same writer lock. No analyzed file is reread after unlock.
    """
    manifest_path = root / "run.manifest.json"
    initial = manifest_path.read_bytes()
    bootstrap = SavedManifest.model_validate_json(initial)
    with RunJournal(root, bootstrap.manifest_sha256, read_only=True) as journal:
        raw_manifest = manifest_path.read_bytes()
        if initial != raw_manifest:
            raise ValueError("Run manifest changed during snapshot acquisition")
        manifest = SavedManifest.model_validate_json(raw_manifest)
        _inventory(manifest)
        states = replay_inventory(
            JOURNAL_EVENTS.validate_python(journal.events), manifest.payload.jobs
        )
        requests = {
            key: state.attempts[0].intent.request
            for key, state in states.items()
            if state.attempts
        }
        if (
            len(requests) == len(manifest.payload.jobs)
            and digest(
                [requests[job.job_id].saved_json() for job in manifest.payload.jobs]
            )
            != manifest.payload.identity.requests_sha256
        ):
            raise ValueError("Runner request inventory differs from saved identity")
        raw_files = {
            manifest_path: raw_manifest,
            root / "journal.sqlite3": (root / "journal.sqlite3").read_bytes(),
        }
        reports = {}
        for path in sorted(set(paths)):
            if not path.is_relative_to(root):
                raise ValueError("Report is outside the saved run")
            reports[path], raw_files[path] = _read_report(
                path, manifest, journal, states
            )
        hashes = {
            path.relative_to(root).as_posix(): hashlib.sha256(raw).hexdigest()
            for path, raw in raw_files.items()
        }
        return VerifiedRun(
            manifest,
            reports,
            requests,
            states,
            hashes,
            journal.head,
            len(journal.events),
        )
