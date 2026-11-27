"""Form explicit groups without losing run, job, case or family identity."""

from collections.abc import Callable, Sequence

from logicmus_eval.analysis.models import (
    AnalysisDiagnostics,
    AnalysisDimensions,
    AnalysisRow,
)
from logicmus_eval.analysis.plan import AnalysisPlan, Group, Selection
from logicmus_eval.analysis.sources import Snapshot, check_compatibility
from logicmus_eval.runner.snapshot_models import TraceIdentity


def rows_for(snapshot: Snapshot, group: str = "") -> list[AnalysisRow]:
    finalized = {}
    for outcome in snapshot.report.details:
        trace = TraceIdentity.model_validate(outcome.inference)
        if trace.job_id in finalized:
            raise ValueError("Outcomes do not map one-to-one to saved job IDs")
        finalized[trace.job_id] = (outcome, trace)
    rows = []
    for job in snapshot.payload.jobs:
        if job.job_id not in finalized:
            continue
        outcome, trace = finalized[job.job_id]
        provenance = outcome.experiment
        if provenance is None:
            raise ValueError("Controlled outcome is missing explicit provenance")
        if trace.request_sha256 != job.request_sha256:
            raise ValueError("Outcome request identity differs from inventory")
        dimensions = AnalysisDimensions(
            group,
            provenance.purpose,
            provenance.series_id,
            provenance.series_kind,
            provenance.pattern_id,
            outcome.mus_size,
            provenance.total_rules,
            job.model_id,
            job.strategy,
        )
        rows.append(
            AnalysisRow(
                dimensions,
                provenance,
                job,
                snapshot.payload.run_id,
                outcome,
                snapshot,
                trace,
            )
        )
    if len(rows) != len(snapshot.report.details):
        raise ValueError("Outcomes do not map one-to-one to saved job IDs")
    return rows


def _group_filter(
    rows: list[AnalysisRow], group: Group, primary: bool
) -> list[AnalysisRow]:
    filters: list[tuple[Sequence[str] | None, Callable[[AnalysisRow], str], str]] = [
        (group.model_ids, lambda row: row.dimensions.model_id, "model_id"),
        (group.strategies, lambda row: row.dimensions.strategy, "strategy"),
        (group.cell_ids, lambda row: row.job.cell_id, "cell_id"),
    ]
    for selected, value, label in filters:
        if selected is not None:
            missing = set(selected) - {value(row) for row in rows}
            if missing and primary:
                raise ValueError(
                    f"Group {group.name}: missing selected {label}: {sorted(missing)}"
                )
            rows = [row for row in rows if value(row) in selected]
    return rows


def group_rows(
    snapshots: list[Snapshot], plan: AnalysisPlan, diagnostics: AnalysisDiagnostics
) -> list[AnalysisRow]:
    runs = {snapshot.payload.run_id: snapshot for snapshot in snapshots}
    requested = {run_id for group in plan.groups for run_id in group.run_ids}
    if requested != runs.keys():
        raise ValueError(
            f"Plan/input run mismatch: missing={sorted(requested - runs.keys())}, "
            f"unselected={sorted(runs.keys() - requested)}"
        )
    all_rows = []
    for group in plan.groups:
        selected = []
        for run_id in dict.fromkeys(group.run_ids):
            snapshot = runs[run_id]
            if plan.mode == "primary":
                if snapshot.payload.identity.config.diagnostic_parent_run is not None:
                    raise ValueError("Diagnostic rerun cannot enter primary analysis")
                if len(snapshot.report.details) != len(snapshot.payload.jobs):
                    raise ValueError(f"Primary analysis requires complete run {run_id}")
            selected.extend(rows_for(snapshot, group.name))
        selected = _group_filter(selected, group, plan.mode == "primary")
        if any(row.dimensions.purpose != plan.purpose for row in selected):
            raise ValueError(
                "Plan purpose differs from saved outcomes; "
                "development and confirmation cannot be pooled"
            )
        identities = [
            (row.job.case_uid, row.dimensions.model_id, row.dimensions.strategy)
            for row in selected
        ]
        if len(identities) != len(set(identities)):
            raise ValueError(
                "Conflicting repeated observations across runs; "
                "explicitly select separate groups/runs"
            )
        diagnostics.compatibility[group.name] = check_compatibility(selected)
        all_rows.extend(selected)
    return sorted(
        all_rows,
        key=lambda row: (
            row.dimensions,
            row.provenance.family_id,
            row.job.case_uid,
            row.job.job_id,
        ),
    )


def select(rows: list[AnalysisRow], selection: Selection) -> list[AnalysisRow]:
    return [
        row
        for row in rows
        if (
            row.dimensions.group == selection.group
            and (
                selection.model_id is None
                or row.dimensions.model_id == selection.model_id
            )
            and (
                selection.strategy is None
                or row.dimensions.strategy == selection.strategy
            )
            and (
                selection.series_id is None
                or row.dimensions.series_id == selection.series_id
            )
            and (
                selection.pattern_id is None
                or row.dimensions.pattern_id == selection.pattern_id
            )
            and (selection.K is None or row.dimensions.k == selection.K)
            and (selection.N is None or row.dimensions.n == selection.N)
        )
    ]
