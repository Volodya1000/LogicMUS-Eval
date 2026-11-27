"""Read-only completion checks shared by runners and analysis consumers."""

import logging
from pathlib import Path

from pydantic import BaseModel, ValidationError

from logicmus_eval.enums import EvaluationStatus, ManifestFilename
from logicmus_eval.models.evaluation import EvaluationSummary

logger = logging.getLogger(__name__)


class ReportConfig(BaseModel):
    name: str
    exp: str
    mus_size: int
    total_rules: int
    pairs: int | None = None


class ReportManifestEntry(BaseModel):
    report: Path
    config: ReportConfig
    model: str
    model_label: str | None = None
    strategy: str
    planned: int | None = None


class IncompleteReportError(ValueError):
    """A returned report is not evidence of a completed evaluation."""


def is_completed(report: EvaluationSummary, expected_cases: int | None = None) -> bool:
    """Require completion evidence, including context for old partial snapshots."""
    count = len(report.details)
    if expected_cases is not None and count != expected_cases:
        return False
    info = report.run_info
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
    candidates = list(directory.glob("*.jsonl"))
    preferred = [
        directory / ManifestFilename.DATASET_JSONL.value,
        directory / "dataset_v1_frozen.jsonl",
    ]
    dataset = next((p for p in preferred if p.is_file()), None)
    if dataset is None and len(candidates) == 1:
        dataset = candidates[0]
    if dataset is None:
        return None
    with dataset.open(encoding="utf-8") as source:
        count = sum(bool(line.strip()) for line in source)
    return min(count, limit) if limit is not None else count


def require_completed_report(
    path: Path,
    *,
    expected_cases: int | None = None,
    limit: int | None = None,
) -> EvaluationSummary:
    report = EvaluationSummary.model_validate_json(path.read_text(encoding="utf-8"))
    if expected_cases is None and (report.status is None or limit is not None):
        selected_limit = (
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
