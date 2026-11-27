"""Validated replay shared by live execution and historical snapshot readers."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from logicmus_eval.models.evaluation import EvaluationCaseReport
from logicmus_eval.runner.preflight import Job, digest
from logicmus_eval.runner.snapshot_models import (
    JOURNAL_EVENTS,
    AttemptResult,
    FinalizedEvent,
    InventoryJob,
    JournalEvent,
    ResponseEvent,
    StartedEvent,
)


@dataclass
class JobState:
    # Compatibility boundary for the existing mutable inference trace serializer.
    attempts: list[dict[str, Any]] = field(default_factory=list)
    outcome: EvaluationCaseReport | None = None

    @property
    def last(self) -> dict[str, Any] | None:
        return self.attempts[-1] if self.attempts else None

    @property
    def indeterminate(self) -> bool:
        return bool(self.last and self.last["status"] == "started")


@dataclass
class SavedAttempt:
    intent: StartedEvent
    result: AttemptResult | None = None

    @property
    def status(
        self,
    ) -> Literal["started", "response", "request_error", "indeterminate_retry"]:
        return self.result.kind if self.result else "started"


@dataclass
class SavedState:
    attempts: list[SavedAttempt] = field(default_factory=list)
    outcome: EvaluationCaseReport | None = None

    @property
    def last(self) -> SavedAttempt | None:
        return self.attempts[-1] if self.attempts else None

    def start(self, event: StartedEvent, job: InventoryJob) -> None:
        if self.last and self.last.status not in {
            "request_error",
            "indeterminate_retry",
        }:
            raise ValueError("attempt started without resolution")
        if event.attempt != len(self.attempts) + 1:
            raise ValueError("nonsequential attempt")
        if (
            event.request_sha256 != job.request_sha256
            or digest(event.request.saved_json()) != job.request_sha256
        ):
            raise ValueError("request identity differs")
        self.attempts.append(SavedAttempt(event))

    def resolve(self, event: AttemptResult) -> None:
        if (
            not self.last
            or self.last.status != "started"
            or event.attempt != len(self.attempts)
        ):
            raise ValueError("attempt result without intent")
        if isinstance(event, ResponseEvent) and event.response_sha256 != digest(
            event.response
        ):
            raise ValueError("response checksum differs")
        self.last.result = event

    def finalize(self, event: FinalizedEvent, job: InventoryJob) -> None:
        if not self.last or self.last.status not in {"response", "request_error"}:
            raise ValueError("finalized without response/error")
        outcome = event.outcome
        if (
            outcome.case_id != job.case_uid
            or outcome.experiment is None
            or outcome.experiment.case_uid != job.case_uid
            or outcome.experiment.cell_id != job.cell_id
        ):
            raise ValueError("outcome differs from planned case")
        self.outcome = outcome


def replay_inventory(
    events: Sequence[JournalEvent], jobs: Sequence[InventoryJob]
) -> dict[str, SavedState]:
    """Check the same state transitions for the runner and read-only consumers."""
    inventory = {job.job_id: job for job in jobs}
    if len(inventory) != len(jobs):
        raise ValueError("Duplicate planned job IDs")
    states = {key: SavedState() for key in inventory}
    try:
        for event in events:
            state, job = states[event.job_id], inventory[event.job_id]
            if state.outcome is not None:
                raise ValueError("event after finalized outcome")
            if isinstance(event, StartedEvent):
                state.start(event, job)
            elif isinstance(event, FinalizedEvent):
                state.finalize(event, job)
            else:
                state.resolve(event)
    except (KeyError, ValueError) as error:
        raise ValueError(f"Run journal is corrupt: {error}") from error
    return states


def replay(events: list[dict[str, Any]], jobs: list[Job]) -> dict[str, JobState]:
    """Keep the live runner's mutable trace API at the serialization boundary."""
    inventory = [
        InventoryJob(
            job_id=job.job_id,
            case_uid=job.case.case_id,
            cell_id=job.case.metadata["cell_id"],
            request_sha256=digest(job.request),
        )
        for job in jobs
    ]
    try:
        saved = replay_inventory(JOURNAL_EVENTS.validate_python(events), inventory)
    except ValueError as error:
        raise ValueError(f"Run journal is corrupt: {error}") from error
    states = {}
    for key, value in saved.items():
        attempts = []
        for attempt in value.attempts:
            payload = attempt.intent.model_dump(
                mode="json", by_alias=True, exclude_unset=True
            )
            if attempt.result is not None:
                payload.update(
                    attempt.result.model_dump(
                        mode="json", by_alias=True, exclude_unset=True
                    )
                )
            payload["status"] = attempt.status
            attempts.append(payload)
        states[key] = JobState(attempts, value.outcome)
    return states
