"""Reproducible offline controlled analysis. No inference module is imported."""
# pylint: disable=too-many-locals

import csv
import json
from pathlib import Path
from typing import Any

from logicmus_eval.analysis.contrasts import contrast_table
from logicmus_eval.analysis.plan import AnalysisPlan
from logicmus_eval.analysis.sources import Snapshot, check_compatibility, load_snapshots
from logicmus_eval.analysis.tables import DIMENSIONS, error_bucket, summary_table
from logicmus_eval.hashing import compute_file_sha256, compute_source_bundle_hash
from logicmus_eval.runner.preflight import digest


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_csv(
    path: Path, rows: list[dict[str, Any]], default_fields: list[str]
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


def _rows(snapshot: Snapshot) -> list[dict[str, Any]]:
    # Root outcomes repeat cases across strategies/models; recover by inventory order,
    # exactly as the verified report projection, rather than joining on local IDs.
    finalized = {
        str(outcome.inference["job_id"]): outcome
        for outcome in snapshot.report.details
        if outcome.inference is not None
    }
    rows = []
    for job in snapshot.payload["jobs"]:
        outcome = finalized.get(job["job_id"])
        if outcome is None:
            continue
        provenance = outcome.experiment
        if provenance is None:
            raise ValueError("Controlled outcome is missing explicit provenance")
        if (
            outcome.inference is None
            or outcome.inference.get("request_sha256") != job["request_sha256"]
        ):
            raise ValueError("Outcome request identity differs from inventory")
        rows.append(
            {
                **provenance.model_dump(),
                **job,
                "run_id": snapshot.payload["run_id"],
                "K": outcome.mus_size,
                "N": provenance.total_rules,
                "outcome": outcome,
                "snapshot": snapshot,
                "error_bucket": error_bucket(outcome),
            }
        )
    if len(rows) != len(snapshot.report.details):
        raise ValueError("Outcomes do not map one-to-one to saved job IDs")
    return rows


def _groups(
    snapshots: list[Snapshot], plan: AnalysisPlan, diagnostics: dict[str, Any]
) -> list[dict[str, Any]]:
    runs = {snapshot.payload["run_id"]: snapshot for snapshot in snapshots}
    requested = {run_id for group in plan.groups for run_id in group.run_ids}
    if requested != runs.keys():
        raise ValueError(
            f"Plan/input run mismatch: missing={sorted(requested - runs.keys())}, "
            f"unselected={sorted(runs.keys() - requested)}"
        )
    all_rows = []
    for group in plan.groups:
        selected: list[dict[str, Any]] = []
        for run_id in dict.fromkeys(group.run_ids):
            snapshot = runs[run_id]
            if plan.mode == "primary":
                if snapshot.payload["identity"]["config"].get("diagnostic_parent_run"):
                    raise ValueError("Diagnostic rerun cannot enter primary analysis")
                if len(snapshot.report.details) != len(snapshot.payload["jobs"]):
                    raise ValueError(f"Primary analysis requires complete run {run_id}")
            selected.extend({**row, "group": group.name} for row in _rows(snapshot))
        for selection, field in [
            (group.model_ids, "model_id"),
            (group.strategies, "strategy"),
            (group.cell_ids, "cell_id"),
        ]:
            if selection is not None:
                missing = set(selection) - {row[field] for row in selected}
                if missing and plan.mode == "primary":
                    raise ValueError(
                        f"Group {group.name}: missing selected {field}: "
                        f"{sorted(missing)}"
                    )
                selected = [row for row in selected if row[field] in selection]
        if any(row["purpose"] != plan.purpose for row in selected):
            raise ValueError(
                "Plan purpose differs from saved outcomes; "
                "development and confirmation cannot be pooled"
            )
        identities = [
            (row["case_uid"], row["model_id"], row["strategy"]) for row in selected
        ]
        if len(identities) != len(set(identities)):
            raise ValueError(
                "Conflicting repeated observations across runs; "
                "explicitly select separate groups/runs"
            )
        diagnostics["compatibility"][group.name] = check_compatibility(selected)
        all_rows.extend(selected)
    return sorted(
        all_rows,
        key=lambda row: tuple(
            str(row[key]) for key in [*DIMENSIONS, "family_id", "case_uid", "job_id"]
        ),
    )


def _legacy(inputs: list[Path], output: Path, manifest: dict[str, Any]) -> None:
    """Describe stored fields only; do not invent provenance or recompute metrics."""
    rows = []
    for path in inputs:
        if not path.is_file():
            raise ValueError("Legacy mode takes explicit JSON/CSV files")
        manifest["inputs"].append(
            {"path": str(path.resolve()), "sha256": compute_file_sha256(path)}
        )
        if path.suffix.lower() == ".csv":
            with path.open(encoding="utf-8", newline="") as stream:
                records = list(csv.DictReader(stream))
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
            records = data if isinstance(data, list) else [data]
        for item in records:
            if item.get("runner_provenance") or item.get("analysis_version"):
                raise ValueError(
                    "Controlled data requires primary/diagnostic verification"
                )
            rows.append(
                {
                    **item,
                    "source": str(path.resolve()),
                    "provenance_status": "legacy",
                    "inference_status": "descriptive-only; no provenance or pairing guarantees",
                }
            )
    write_csv(output / "legacy.csv", rows, ["source", "provenance_status"])


def analyze(
    inputs: list[Path], plan: AnalysisPlan, output: Path, *, plots: bool = False
) -> None:
    """Write a fresh artifact directory, including diagnostics on rejected analyses."""
    output = output.resolve()
    for supplied in inputs:
        path = supplied.resolve()
        roots = (
            [path]
            if path.is_dir()
            else [
                parent
                for parent in path.parents
                if (parent / "run.manifest.json").is_file()
            ]
        )
        if output == path or any(
            output == root or output.is_relative_to(root) for root in roots
        ):
            raise ValueError("Output must be separate from input sources")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("Output directory must be empty; use a fresh destination")
    diagnostics: dict[str, Any] = {
        "mode": plan.mode,
        "runs": [],
        "compatibility": {},
        "contrasts": [],
    }
    manifest: dict[str, Any] = {
        "analysis_version": plan.analysis_version,
        "plan": plan.model_dump(),
        "plan_sha256": digest(plan.model_dump()),
        "methods": plan.intervals.model_dump(),
        "scope": "pointwise",
        "analyzer_source_bundle_sha256": compute_source_bundle_hash(),
        "inputs": [],
        "status": "rejected",
    }
    try:
        if plan.mode == "legacy":
            _legacy(inputs, output, manifest)
        else:
            snapshots = load_snapshots(inputs)
            manifest["inputs"] = [snapshot.evidence for snapshot in snapshots]
            diagnostics["runs"] = [
                {
                    "run_id": snapshot.payload["run_id"],
                    "planned": len(snapshot.payload["jobs"]),
                    "processed": len(snapshot.report.details),
                    "provenance": snapshot.report.runner_provenance,
                    "missing_job_ids": [
                        job["job_id"]
                        for job in snapshot.payload["jobs"]
                        if job["job_id"]
                        not in {
                            str((r.inference or {}).get("job_id"))
                            for r in snapshot.report.details
                        }
                    ],
                }
                for snapshot in snapshots
            ]
            rows = _groups(snapshots, plan, diagnostics)
            cases = []
            for row in rows:
                outcome = row["outcome"]
                cases.append(
                    {
                        **{
                            key: value
                            for key, value in row.items()
                            if key not in {"outcome", "snapshot"}
                        },
                        **outcome.model_dump(
                            exclude={
                                "experiment",
                                "metadata",
                                "inference",
                                "raw_response",
                                "generated_code",
                                "reasoning",
                            }
                        ),
                        **outcome.metadata.model_dump(),
                    }
                )
            write_csv(
                output / "cases.csv",
                cases,
                [*DIMENSIONS, "run_id", "job_id", "case_uid", "family_id"],
            )
            if plan.mode == "primary":
                summaries = summary_table(rows, plan)
                contrasts = contrast_table(rows, plan, diagnostics["contrasts"])
            else:
                summaries, contrasts = [], []
                diagnostics["notice"] = (
                    "Diagnostic description only; incomplete/diagnostic data "
                    "are not a full experiment."
                )
            write_csv(output / "summary.csv", summaries, DIMENSIONS)
            write_csv(
                output / "contrasts.csv",
                contrasts,
                ["name", "metric", "estimate", "low", "high", "families"],
            )
        manifest["status"] = "complete"
    except (ValueError, OSError, KeyError) as error:
        diagnostics["error"] = str(error)
        raise
    finally:
        write_json(output / "diagnostics.json", diagnostics)
        manifest["artifacts"] = {
            path.name: compute_file_sha256(path)
            for path in sorted(output.glob("*.csv"))
        }
        write_json(output / "analysis.manifest.json", manifest)
    if plots and plan.mode == "primary":
        # pylint: disable=import-outside-toplevel
        from logicmus_eval.analysis.plotting import (
            plot_tables,  # pylint: disable=import-outside-toplevel
        )

        plot_tables(output)
