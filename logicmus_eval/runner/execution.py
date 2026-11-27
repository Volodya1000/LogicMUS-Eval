"""New/resume orchestration using the existing case pipeline and metric set."""

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from logicmus_eval.enums import EvaluationErrorType
from logicmus_eval.evaluation.metrics import build_metrics
from logicmus_eval.evaluation.pipeline import EvaluationPipeline
from logicmus_eval.evaluation.strategies import (
    DirectEvaluationStrategy,
    Z3TranslationEvaluationStrategy,
)
from logicmus_eval.extractor_metadata import extract_usage_metadata
from logicmus_eval.models.evaluation import (
    Z3_EXECUTION_PROTOCOL_VERSION,
    EvaluationSummary,
)
from logicmus_eval.runner.config import RunConfig
from logicmus_eval.runner.journal import RunJournal, atomic_json
from logicmus_eval.runner.manifest import resume_preflight
from logicmus_eval.runner.preflight import Preflight, digest, preflight
from logicmus_eval.runner.state import JobState, replay
from logicmus_eval.sandbox.executor import Z3CodeExecutor

Completion = Callable[..., object]
IndeterminatePolicy = Literal["halt", "retry"]


def _snapshot(  # pylint: disable=too-many-locals
    root: Path, manifest: dict[str, Any], ready: Preflight, journal: RunJournal
) -> EvaluationSummary:
    states = replay(journal.events, ready.jobs)
    details = [
        states[job.job_id].outcome
        for job in ready.jobs
        if states[job.job_id].outcome is not None
    ]
    # The explicit list avoids any historical-report fallback or recomputation of
    # eligibility; only finalized reports feed the existing metrics.
    outcomes = [outcome for outcome in details if outcome is not None]
    pipeline = EvaluationPipeline(DirectEvaluationStrategy(), None, build_metrics())
    report = pipeline.from_outcomes(outcomes, len(ready.jobs))
    attempts = [attempt for state in states.values() for attempt in state.attempts]
    report.runner_provenance = {
        "protocol": "controlled-run-v1",
        "run_id": manifest["payload"]["run_id"],
        "manifest_sha256": manifest["manifest_sha256"],
        "identity_sha256": ready.identity_hash,
        "source_bundle_sha256": ready.identity["source_bundle_sha256"],
        "journal_head_sha256": journal.head,
        "journal_event_count": len(journal.events),
        "finalized": len(outcomes),
        "planned": len(ready.jobs),
        "pending": sum(not state.attempts for state in states.values()),
        "indeterminate": sum(state.indeterminate for state in states.values()),
        "responses_awaiting_processing": sum(
            state.outcome is None
            and state.last is not None
            and state.last["status"] == "response"
            for state in states.values()
        ),
        "indeterminate_attempts": sum(
            attempt["status"] in {"started", "indeterminate_retry"}
            for attempt in attempts
        ),
        "attempts_with_unknown_cost": sum(
            attempt["status"] != "response"
            or extract_usage_metadata(attempt.get("response"), 0).total_tokens is None
            for attempt in attempts
        ),
        "http_attempts": len(attempts),
    }
    report.z3_execution_protocol_version = (
        Z3_EXECUTION_PROTOCOL_VERSION if "z3" in ready.config.strategies else None
    )
    atomic_json(root / "report.json", report.model_dump(mode="json"))
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    for model in ready.config.models:
        for strategy in ready.config.strategies:
            selected = [
                job
                for job in ready.jobs
                if job.model.model_id == model.model_id and job.strategy == strategy
            ]
            selected_outcomes = [states[job.job_id].outcome for job in selected]
            subgroup = pipeline.from_outcomes(
                [outcome for outcome in selected_outcomes if outcome is not None],
                len(selected),
            )
            subgroup.runner_provenance = {
                **report.runner_provenance,
                "model_id": model.model_id,
                "strategy": strategy,
            }
            subgroup.z3_execution_protocol_version = (
                Z3_EXECUTION_PROTOCOL_VERSION if strategy == "z3" else None
            )
            atomic_json(
                reports / f"{digest([model.model_id, strategy])}.json",
                subgroup.model_dump(mode="json"),
            )
    return report


def _execute(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    root: Path,
    manifest: dict[str, Any],
    ready: Preflight,
    journal: RunJournal,
    policy: IndeterminatePolicy,
    completion: Completion | None,
) -> EvaluationSummary:
    # pylint: disable=import-outside-toplevel
    # Import only after full-series admission, compatibility, lock and journal
    # validation. The offline command never imports this module's network peer.
    from logicmus_eval.runner.inference import (
        JournalExtractor,  # pylint: disable=import-outside-toplevel
    )

    states = replay(journal.events, ready.jobs)
    if any(
        state.outcome is not None
        and state.outcome.error_type is EvaluationErrorType.MODEL_PROFILE_MISMATCH
        for state in states.values()
    ):
        raise ValueError(
            "Saved model profile mismatch; use a new run for changed conditions"
        )
    if policy not in {"halt", "retry"}:
        raise ValueError("indeterminate_policy must be halt or retry")
    if policy == "halt" and any(state.indeterminate for state in states.values()):
        _snapshot(root, manifest, ready, journal)
        raise ValueError(
            "Run contains indeterminate HTTP attempts; inspect history and explicitly choose retry"
        )
    try:
        for job in ready.jobs:
            state: JobState = states[job.job_id]
            if state.outcome is not None:
                continue
            recovered_processing = bool(state.attempts)
            if state.indeterminate:
                event = {
                    "kind": "indeterminate_retry",
                    "job_id": job.job_id,
                    "attempt": len(state.attempts),
                    "at": datetime.now(UTC).isoformat(),
                    "policy": "retry",
                    "previous_request_may_have_been_processed": True,
                    "previous_cost": "unknown",
                }
                journal.append(event)
                assert state.last is not None
                state.last.update(event)
                state.last["status"] = "indeterminate_retry"
            extractor = JournalExtractor(ready.config, job, state, journal, completion)
            strategy = (
                DirectEvaluationStrategy()
                if job.strategy == "direct"
                else Z3TranslationEvaluationStrategy(
                    Z3CodeExecutor(ready.config.z3_timeout_seconds)
                )
            )
            pipeline = EvaluationPipeline(strategy, extractor, build_metrics())
            outcome = pipeline.evaluate_case(job.case)
            if recovered_processing:
                # Wall time of interrupted processing is unobserved. Request
                # timings remain available in the persisted attempt history.
                outcome.metadata.case_latency_seconds = None
            extractor.trace["recovered_processing"] = recovered_processing
            outcome.inference = extractor.trace
            journal.append(
                {
                    "kind": "finalized",
                    "job_id": job.job_id,
                    "at": datetime.now(UTC).isoformat(),
                    "outcome": outcome.model_dump(mode="json"),
                }
            )
            state.outcome = outcome
            if outcome.error_type is EvaluationErrorType.MODEL_PROFILE_MISMATCH:
                raise ValueError(
                    "Observed model profile mismatch; outcome saved, stopping further HTTP"
                )
    finally:
        report = _snapshot(root, manifest, ready, journal)
    return report


def new_run(
    config: RunConfig, root: Path, *, completion: Completion | None = None
) -> EvaluationSummary:
    ready = preflight(config)
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    payload = {
        "run_id": str(uuid4()),
        "created_at": datetime.now(UTC).isoformat(),
        "identity": ready.identity,
        "job_ids": [job.job_id for job in ready.jobs],
        "jobs": [
            {
                "job_id": job.job_id,
                "case_uid": job.case.case_id,
                "cell_id": job.case.metadata["cell_id"],
                "model_id": job.model.model_id,
                "strategy": job.strategy,
                "request_sha256": digest(job.request),
            }
            for job in ready.jobs
        ],
    }
    manifest: dict[str, Any] = {"payload": payload, "manifest_sha256": digest(payload)}
    with RunJournal(root, manifest["manifest_sha256"], create=True) as journal:
        atomic_json(root / "run.manifest.json", manifest)
        _snapshot(root, manifest, ready, journal)
        return _execute(root, manifest, ready, journal, "halt", completion)


def resume_run(
    root: Path,
    *,
    config: RunConfig | None = None,
    indeterminate_policy: IndeterminatePolicy = "halt",
    completion: Completion | None = None,
) -> EvaluationSummary:
    root = root.resolve()
    manifest = json.loads((root / "run.manifest.json").read_text(encoding="utf-8"))
    with RunJournal(root, manifest["manifest_sha256"]) as journal:
        manifest, ready = resume_preflight(root, config)
        return _execute(
            root, manifest, ready, journal, indeterminate_policy, completion
        )
