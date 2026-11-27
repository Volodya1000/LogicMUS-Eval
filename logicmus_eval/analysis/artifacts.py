"""CSV serialization and atomic, truthful publication of analysis artifacts."""

import csv
import json
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

from pydantic import BaseModel, JsonValue

from logicmus_eval.analysis.models import (
    AnalysisDiagnostics,
    AnalysisDimensions,
    AnalysisManifest,
    AnalysisRow,
    ContrastResult,
    SummaryResult,
)
from logicmus_eval.analysis.plan import AnalysisPlan
from logicmus_eval.analysis.tables import DIMENSIONS, error_bucket
from logicmus_eval.hashing import compute_file_sha256
from logicmus_eval.runner.journal import atomic_json
from logicmus_eval.runner.snapshot_models import JSON_OBJECT


def json_record(
    value: BaseModel, *, exclude_none: bool = False
) -> dict[str, JsonValue]:
    return JSON_OBJECT.validate_python(
        value.model_dump(mode="json", exclude_none=exclude_none)
    )


def write_json(path: Path, value: Mapping[str, JsonValue]) -> None:
    atomic_json(path, value)


def write_csv(
    path: Path, rows: Sequence[Mapping[str, JsonValue]], default_fields: list[str]
) -> None:
    fields = list(
        dict.fromkeys([*default_fields, *(key for row in rows for key in row)])
    )
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (list, dict))
                    else value
                    for key, value in row.items()
                }
            )


def dimensions_record(value: AnalysisDimensions) -> dict[str, JsonValue]:
    return {
        "group": value.group,
        "purpose": value.purpose,
        "series_id": value.series_id,
        "series_kind": value.series_kind,
        "pattern_id": value.pattern_id,
        "K": value.k,
        "N": value.n,
        "model_id": value.model_id,
        "strategy": value.strategy,
    }


def case_record(row: AnalysisRow) -> dict[str, JsonValue]:
    outcome = row.outcome
    # Nullable scores/usage must remain present as null, unlike optional diagnostic keys.
    record = JSON_OBJECT.validate_python(row.provenance.model_dump(mode="json"))
    record.update(row.job.saved_json())
    record.update(dimensions_record(row.dimensions))
    record.update({"run_id": row.run_id, "error_bucket": error_bucket(outcome)})
    record.update(
        JSON_OBJECT.validate_python(
            outcome.model_dump(
                mode="json",
                exclude={
                    "experiment",
                    "metadata",
                    "inference",
                    "raw_response",
                    "generated_code",
                    "reasoning",
                },
            )
        )
    )
    record.update(JSON_OBJECT.validate_python(outcome.metadata.model_dump(mode="json")))
    return record


def summary_record(row: SummaryResult) -> dict[str, JsonValue]:
    record = dimensions_record(row.dimensions) | row.metrics
    record.update(
        JSON_OBJECT.validate_python(
            {
                "families": row.families,
                "unsat_families": row.unsat_families,
                "run_ids": row.run_ids,
                "error_bucket_counts": row.error_bucket_counts,
                "error_bucket_fractions": row.error_bucket_fractions,
            }
        )
    )
    for metric, interval in row.intervals.items():
        record.update(
            {
                f"{metric}_ci_{key}": value
                for key, value in JSON_OBJECT.validate_python(interval).items()
            }
        )
    return record


def contrast_record(row: ContrastResult) -> dict[str, JsonValue]:
    return {
        "name": row.name,
        "kind": row.kind,
        "metric": row.metric,
        "direction": row.direction,
        "left": json_record(row.left, exclude_none=True),
        "right": json_record(row.right, exclude_none=True),
        "pairs": row.pairs,
        "estimate": row.estimate,
        **JSON_OBJECT.validate_python(row.interval),
    }


def write_cases(output: Path, rows: list[AnalysisRow]) -> None:
    write_csv(
        output / "cases.csv",
        [case_record(row) for row in rows],
        [*DIMENSIONS, "run_id", "job_id", "case_uid", "family_id"],
    )


def write_summaries(output: Path, rows: list[SummaryResult]) -> None:
    write_csv(output / "summary.csv", [summary_record(row) for row in rows], DIMENSIONS)


def write_contrasts(output: Path, rows: list[ContrastResult]) -> None:
    write_csv(
        output / "contrasts.csv",
        [contrast_record(row) for row in rows],
        ["name", "metric", "estimate", "low", "high", "families"],
    )


def figure_names(plan: AnalysisPlan) -> list[str]:
    return [
        f"figures/{kind}_{metric}.png"
        for kind in ("noise_sweep", "k_sweep", "topology_panel")
        for metric in dict.fromkeys([plan.primary_metric, *plan.additional_metrics])
    ] + ["figures/coverage_errors.png", "figures/paired_differences.png"]


def verify_artifacts(root: Path, manifest: AnalysisManifest) -> None:
    required = {"cases.csv", "summary.csv", "contrasts.csv"}
    if not required <= manifest.artifacts.keys():
        raise ValueError("Required analysis table hashes are missing")
    for name, checksum in manifest.artifacts.items():
        path = (root / name).resolve()
        if (
            not path.is_relative_to(root.resolve())
            or not path.is_file()
            or compute_file_sha256(path) != checksum
        ):
            raise ValueError(f"Analysis table/artifact changed: {name}")


def publish(
    root: Path, manifest: AnalysisManifest, diagnostics: AnalysisDiagnostics
) -> None:
    write_json(root / "diagnostics.json", json_record(diagnostics, exclude_none=True))
    manifest.artifacts = {
        path.relative_to(root).as_posix(): compute_file_sha256(path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path != root / "analysis.manifest.json"
    }
    write_json(root / "analysis.manifest.json", json_record(manifest))


def _require_outputs(root: Path, manifest: AnalysisManifest) -> None:
    expected = (
        ["legacy.csv"]
        if manifest.plan.mode == "legacy"
        else ["cases.csv", "summary.csv", "contrasts.csv"]
    )
    if manifest.plots_requested:
        expected += figure_names(manifest.plan)
    missing = [name for name in expected if not (root / name).is_file()]
    if missing:
        raise ValueError(f"Requested artifacts are missing: {missing}")


@contextmanager
def publication(
    root: Path, manifest: AnalysisManifest, diagnostics: AnalysisDiagnostics
) -> Iterator[None]:
    """Leave running on a hard crash, rejected on an exception, complete only last."""
    manifest.status = "running"
    publish(root, manifest, diagnostics)
    try:
        yield
        _require_outputs(root, manifest)
    except BaseException as error:
        diagnostics.error = str(error) or type(error).__name__
        manifest.status = "rejected"
        raise
    else:
        manifest.status = "complete"
    finally:
        try:
            publish(root, manifest, diagnostics)
        except OSError as error:
            manifest.status = "rejected"
            diagnostics.error = (
                (diagnostics.error + "; ") if diagnostics.error else ""
            ) + str(error)
            try:
                publish(root, manifest, diagnostics)
            except OSError as rejection_error:
                error.add_note(f"Could not publish rejection state: {rejection_error}")
            raise
