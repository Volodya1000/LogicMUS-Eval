"""Read-only completion checks shared by runners and analysis consumers."""

import logging
from pathlib import Path
from typing import TextIO

from pydantic import JsonValue, ValidationError

from logicmus_eval.enums import EvaluationStatus, ManifestFilename
from logicmus_eval.errors import IncompleteReportError
from logicmus_eval.models.evaluation import EvaluationSummary, RunInfo
from logicmus_eval.models.report_manifest import ReportConfig, ReportManifestEntry

__all__: list[str] = [
    "IncompleteReportError",
    "ReportConfig",
    "ReportManifestEntry",
    "is_completed",
    "report_is_complete",
    "require_completed_report",
]

logger: logging.Logger = logging.getLogger(__name__)


def is_completed(report: EvaluationSummary, expected_cases: int | None = None) -> bool:
    """Require completion evidence, including context for old partial snapshots."""
    count: int = len(report.details)
    if expected_cases is not None and count != expected_cases:
        return False
    info: RunInfo | None = report.run_info
    if info is not None and (
        info.finished_at is None or info.total_cases_processed != count
    ):
        return False
    if report.status is None:
        return (
            report.report_schema_version is None
            and report.metric_definitions_version is None
            and (info is not None or expected_cases is not None)
        )
    if report.status is not EvaluationStatus.COMPLETED:
        return False
    if report.report_schema_version not in {
        2,
        3,
    } or report.metric_definitions_version not in {"2", "3"}:
        return False
    planned: JsonValue
    processed: JsonValue
    planned, processed = report.metrics.get("planned"), report.metrics.get("processed")
    return (
        isinstance(planned, int)
        and not isinstance(planned, bool)
        and isinstance(processed, int)
        and not isinstance(processed, bool)
        and planned == processed == count
    )


def _dataset_count(directory: Path, limit: int | None) -> int | None:
    """Match evaluation's versioned/legacy filename priority without inference."""
    if limit is not None and limit < 0:
        raise ValueError("limit must be nonnegative")
    candidates: list[Path] = list(directory.glob("*.jsonl"))
    preferred: list[Path] = [
        directory / ManifestFilename.DATASET_JSONL.value,
        directory / "dataset_v1_frozen.jsonl",
    ]
    dataset: Path | None = next((p for p in preferred if p.is_file()), None)
    if dataset is None and len(candidates) == 1:
        dataset = candidates[0]
    if dataset is None:
        return None
    source: TextIO
    with dataset.open(encoding="utf-8") as source:
        count: int = sum(bool(line.strip()) for line in source)
    return min(count, limit) if limit is not None else count


def require_completed_report(
    path: Path,
    *,
    expected_cases: int | None = None,
    limit: int | None = None,
) -> EvaluationSummary:
    report: EvaluationSummary = EvaluationSummary.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if expected_cases is None and (report.status is None or limit is not None):
        selected_limit: int | None = (
            limit
            if limit is not None
            else report.run_info.limit
            if report.run_info
            else None
        )
        expected_cases = _dataset_count(path.parent, selected_limit)
    if not is_completed(report, expected_cases):
        raise IncompleteReportError(
            f"Incomplete or unsupported evaluation report: {path}"
        )
    return report


def report_is_complete(
    path: Path, *, expected_cases: int | None = None, limit: int | None = None
) -> bool:
    """Malformed/partial/unsupported files must not suppress a fresh evaluation."""
    try:
        require_completed_report(path, expected_cases=expected_cases, limit=limit)
    except FileNotFoundError:
        return False
    except (ValidationError, IncompleteReportError) as exc:
        logger.warning("Ignoring report %s: %s", path, exc)
        return False
    return True


def verify_runner_report(path: Path) -> EvaluationSummary:
    """Verify a new runner report against its manifest and committed journal.

    This checks the saved experiment, without requiring today's sources to match
    the historical run. Resume additionally checks the current executable bundle.
    Hashes detect accidental corruption; they are not signatures against tampering.
    """
    # pylint: disable=too-many-locals,import-outside-toplevel
    import json  # pylint: disable=import-outside-toplevel

    from logicmus_eval.evaluation.metrics import (
        build_metrics,  # pylint: disable=import-outside-toplevel
    )
    from logicmus_eval.evaluation.pipeline import (
        EvaluationPipeline,  # pylint: disable=import-outside-toplevel
    )
    from logicmus_eval.evaluation.strategies import (
        DirectEvaluationStrategy,  # pylint: disable=import-outside-toplevel
    )
    from logicmus_eval.models.evaluation import (
        EvaluationCaseReport,  # pylint: disable=import-outside-toplevel
    )
    from logicmus_eval.runner.journal import (
        RunJournal,  # pylint: disable=import-outside-toplevel
    )
    from logicmus_eval.runner.preflight import (
        digest,  # pylint: disable=import-outside-toplevel
    )

    report = EvaluationSummary.model_validate_json(path.read_text(encoding="utf-8"))
    provenance = report.runner_provenance
    root = next(
        (
            p
            for p in (path.parent, path.parent.parent)
            if (p / "run.manifest.json").is_file()
        ),
        None,
    )
    if provenance is None or root is None:
        raise ValueError(
            "Runner provenance is unavailable; historical reports are not upgraded"
        )
    manifest = json.loads((root / "run.manifest.json").read_text(encoding="utf-8"))
    payload = manifest["payload"]
    if (
        manifest["manifest_sha256"] != digest(payload)
        or provenance.get("manifest_sha256") != manifest["manifest_sha256"]
        or provenance.get("run_id") != payload["run_id"]
        or provenance.get("identity_sha256") != digest(payload["identity"])
        or provenance.get("source_bundle_sha256")
        != payload["identity"]["source_bundle_sha256"]
    ):
        raise ValueError("Runner provenance differs from manifest")
    selected = [
        job
        for job in payload["jobs"]
        if ("model_id" not in provenance or job["model_id"] == provenance["model_id"])
        and ("strategy" not in provenance or job["strategy"] == provenance["strategy"])
    ]
    with RunJournal(root.resolve(), manifest["manifest_sha256"]) as journal:
        if provenance.get("journal_head_sha256") != journal.head or provenance.get(
            "journal_event_count"
        ) != len(journal.events):
            raise ValueError(
                "Runner provenance differs from journal head; rebuild stale report"
            )
        finalized = {
            event["job_id"]: event["outcome"]
            for event in journal.events
            if event["kind"] == "finalized"
        }
        expected = [
            EvaluationCaseReport.model_validate(finalized[job["job_id"]])
            for job in selected
            if job["job_id"] in finalized
        ]
    rebuilt = EvaluationPipeline(
        DirectEvaluationStrategy(), None, build_metrics()
    ).from_outcomes(expected, len(selected))
    if (
        report.details != expected
        or report.metrics != rebuilt.metrics
        or report.status != rebuilt.status
    ):
        raise ValueError(
            "Runner report provenance does not match committed outcomes/metrics"
        )
    return report
