"""Offline analysis orchestration; computation and publication have explicit stages."""

from pathlib import Path

from logicmus_eval.analysis.artifacts import (
    publication,
    publish,
    write_cases,
    write_contrasts,
    write_summaries,
)
from logicmus_eval.analysis.contrasts import contrast_table
from logicmus_eval.analysis.legacy import describe
from logicmus_eval.analysis.models import (
    AnalysisDiagnostics,
    AnalysisManifest,
    RunDiagnostic,
)
from logicmus_eval.analysis.plan import AnalysisPlan
from logicmus_eval.analysis.selection import group_rows
from logicmus_eval.analysis.sources import Snapshot, load_snapshots
from logicmus_eval.analysis.tables import summary_table
from logicmus_eval.hashing import compute_source_bundle_hash
from logicmus_eval.runner.preflight import digest
from logicmus_eval.runner.snapshot_models import RunnerProvenance, TraceIdentity


def _prepare_output(inputs: list[Path], output: Path) -> None:
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


def _run_diagnostic(snapshot: Snapshot) -> RunDiagnostic:
    finalized = {
        TraceIdentity.model_validate(outcome.inference).job_id
        for outcome in snapshot.report.details
    }
    return RunDiagnostic(
        run_id=snapshot.payload.run_id,
        planned=len(snapshot.payload.jobs),
        processed=len(snapshot.report.details),
        provenance=RunnerProvenance.model_validate(snapshot.report.runner_provenance),
        missing_job_ids=[
            job.job_id for job in snapshot.payload.jobs if job.job_id not in finalized
        ],
    )


def _controlled(
    inputs: list[Path],
    output: Path,
    manifest: AnalysisManifest,
    diagnostics: AnalysisDiagnostics,
) -> None:
    snapshots = load_snapshots(inputs)
    manifest.inputs = [snapshot.evidence for snapshot in snapshots]
    diagnostics.runs = [_run_diagnostic(snapshot) for snapshot in snapshots]
    rows = group_rows(snapshots, manifest.plan, diagnostics)
    write_cases(output, rows)
    summaries = (
        summary_table(rows, manifest.plan) if manifest.plan.mode == "primary" else []
    )
    write_summaries(output, summaries)
    contrasts = (
        contrast_table(rows, manifest.plan, diagnostics.contrasts)
        if manifest.plan.mode == "primary"
        else []
    )
    write_contrasts(output, contrasts)
    if manifest.plan.mode != "primary":
        diagnostics.notice = (
            "Diagnostic description only; incomplete/diagnostic data "
            "are not a full experiment."
        )


def analyze(
    inputs: list[Path], plan: AnalysisPlan, output: Path, *, plots: bool = False
) -> None:
    """Public API: write fresh artifacts, retaining partial evidence on any failure."""
    output = output.resolve()
    _prepare_output(inputs, output)
    manifest = AnalysisManifest(
        analysis_version=plan.analysis_version,
        plan=plan,
        plan_sha256=digest(plan.model_dump(mode="json")),
        methods=plan.intervals,
        analyzer_source_bundle_sha256=compute_source_bundle_hash(),
        plots_requested=plots and plan.mode == "primary",
    )
    diagnostics = AnalysisDiagnostics(mode=plan.mode)
    with publication(output, manifest, diagnostics):
        if plan.mode == "legacy":
            describe(inputs, output, manifest)
        else:
            _controlled(inputs, output, manifest, diagnostics)
        if manifest.plots_requested:
            # Optional plotting dependencies are only imported when requested.
            # pylint: disable=import-outside-toplevel
            from logicmus_eval.analysis.plotting import (
                plot_tables,  # pylint: disable=import-outside-toplevel
            )

            publish(output, manifest, diagnostics)
            plot_tables(output, finalize=False)
