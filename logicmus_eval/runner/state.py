"""Validated replay of journal events, available to offline preflight."""

from dataclasses import dataclass, field
from typing import Any

from logicmus_eval.models.evaluation import EvaluationCaseReport
from logicmus_eval.runner.preflight import Job, digest


@dataclass
class JobState:
    attempts: list[dict[str, Any]] = field(default_factory=list)
    outcome: EvaluationCaseReport | None = None

    @property
    def last(self) -> dict[str, Any] | None:
        return self.attempts[-1] if self.attempts else None

    @property
    def indeterminate(self) -> bool:
        return bool(self.last and self.last["status"] == "started")


def replay(  # pylint: disable=too-many-branches
    events: list[dict[str, Any]], jobs: list[Job]
) -> dict[str, JobState]:
    return replay_inventory(
        events,
        [
            {
                "job_id": job.job_id,
                "case_uid": job.case.case_id,
                "cell_id": job.case.metadata["cell_id"],
                "request_sha256": digest(job.request),
            }
            for job in jobs
        ],
    )


def replay_inventory(  # pylint: disable=too-many-branches
    events: list[dict[str, Any]], jobs: list[dict[str, Any]]
) -> dict[str, JobState]:
    """Validate historical state using saved inventory, without current sources."""
    inventory = {job["job_id"]: job for job in jobs}
    if len(inventory) != len(jobs):
        raise ValueError("Duplicate planned job IDs")
    states = {key: JobState() for key in inventory}
    try:
        for event in events:
            uid = event["job_id"]
            state = states[uid]
            job = inventory[uid]
            if state.outcome is not None:
                raise ValueError("event after finalized outcome")
            kind = event["kind"]
            if kind == "started":
                if state.last and state.last["status"] not in {
                    "request_error",
                    "indeterminate_retry",
                }:
                    raise ValueError("attempt started without resolution")
                if event["attempt"] != len(state.attempts) + 1:
                    raise ValueError("nonsequential attempt")
                if (
                    event["request_sha256"] != job["request_sha256"]
                    or digest(event["request"]) != job["request_sha256"]
                ):
                    raise ValueError("request identity differs")
                state.attempts.append({**event, "status": "started"})
            elif kind in {"response", "request_error", "indeterminate_retry"}:
                if (
                    not state.last
                    or state.last["status"] != "started"
                    or event["attempt"] != len(state.attempts)
                ):
                    raise ValueError("attempt result without intent")
                if kind == "response" and event["response_sha256"] != digest(
                    event["response"]
                ):
                    raise ValueError("response checksum differs")
                state.last.update(event)
                state.last["status"] = kind
            elif kind == "finalized":
                if not state.last or state.last["status"] not in {
                    "response",
                    "request_error",
                }:
                    raise ValueError("finalized without response/error")
                outcome = EvaluationCaseReport.model_validate(event["outcome"])
                if (
                    outcome.case_id != job["case_uid"]
                    or outcome.experiment is None
                    or outcome.experiment.case_uid != job["case_uid"]
                    or outcome.experiment.cell_id != job["cell_id"]
                ):
                    raise ValueError("outcome differs from planned case")
                state.outcome = outcome
            else:
                raise ValueError("unknown event kind")
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Run journal is corrupt: {error}") from error
    return states
