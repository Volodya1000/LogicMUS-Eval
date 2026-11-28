"""Hash, resume and analysis-artifact validation shared by smoke evidence versions."""

from pathlib import Path

from logicmus_eval.analysis.models import AnalysisManifest, RunEvidence
from logicmus_eval.confirmation.io import local, read_json
from logicmus_eval.confirmation.models import SmokeEvidence
from logicmus_eval.hashing import compute_file_sha256
from logicmus_eval.runner.preflight import digest
from logicmus_eval.runner.snapshot import read_snapshot


def _artifacts(root: Path, artifacts: dict[str, str]) -> None:
    for name, checksum in artifacts.items():
        if compute_file_sha256(local(root, name)) != checksum:
            raise ValueError(f"Operator evidence hash differs: {name}")


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
    required_mode = (
        "diagnostic"
        if evidence.evidence_version == "infrastructure-smoke-v1"
        else "primary"
    )
    if (
        plan.purpose != "development"
        or plan.mode != required_mode
        or manifest.plan_sha256 != digest(plan.model_dump(mode="json"))
        or manifest.methods != plan.intervals
        or {r for g in plan.groups for r in g.run_ids} != {run_id}
    ):
        raise ValueError(
            f"Smoke analysis must be {required_mode} and select exactly the development smoke UUID"
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
