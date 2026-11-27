"""Journal-backed extraction; this is the only controlled network boundary."""

import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from logicmus_eval.enums import EvaluationErrorStage, EvaluationErrorType
from logicmus_eval.errors import ExtractorError
from logicmus_eval.extractor_metadata import extract_usage_metadata, response_field
from logicmus_eval.models.evaluation import ExtractionMetadata
from logicmus_eval.models.extraction import ExtractionResult
from logicmus_eval.response_processing import parse_response
from logicmus_eval.runner.config import ModelProfile, RunConfig
from logicmus_eval.runner.journal import RunJournal
from logicmus_eval.runner.preflight import Job, digest
from logicmus_eval.runner.state import JobState
from logicmus_eval.runner.transport import TransportError, request_completion

Completion = Callable[..., object]


def snapshot_response(
    response: object, credential: str | None = None
) -> dict[str, Any]:
    """Persist the API envelope, excluding SDK private fields and HTTP headers.

    The original choices/content/usage are retained, before any interpretation.
    SDK transport internals can contain Authorization and must never be dumped.
    """

    def plain(value: object) -> Any:
        if isinstance(value, BaseModel):
            return plain(value.model_dump(mode="json"))
        if isinstance(value, dict):
            return {
                str(key): plain(item)
                for key, item in value.items()
                if str(key).lower()
                not in {"authorization", "api_key", "headers", "access_token", "secret"}
            }
        if isinstance(value, (list, tuple)):
            return [plain(item) for item in value]
        if isinstance(value, str) and credential:
            return value.replace(credential, "[REDACTED]")
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        raise TypeError("Response envelope is not JSON serializable")

    envelope = {
        key: plain(response_field(response, key))
        for key in (
            "id",
            "object",
            "created",
            "model",
            "system_fingerprint",
            "choices",
            "usage",
            "request_id",
            "raw_body",
            "http_status",
            "body_json_error",
            "error",
            "model_info",
        )
    }
    # Preserve original body text unless credential/sensitive-field removal is
    # necessary. Do not retain a second, unsanitized copy inside raw_body.
    raw_body = envelope.get("raw_body")
    if isinstance(raw_body, str):
        try:
            parsed = json.loads(raw_body)
            sanitized = plain(parsed)
            if parsed != sanitized:
                envelope["raw_body"] = json.dumps(sanitized, ensure_ascii=False)
        except ValueError:
            pass
    return envelope


def observed_profile(raw: dict[str, Any]) -> dict[str, Any]:
    info = raw.get("model_info")
    info = info if isinstance(info, dict) else {}
    return {
        "model_id": raw.get("model"),
        "system_fingerprint": raw.get("system_fingerprint"),
        **{
            key: info.get(key)
            for key in ModelProfile.model_fields  # pylint: disable=not-an-iterable
            if key != "served_model_id"
        },
    }


class JournalExtractor:
    def __init__(
        self,
        config: RunConfig,
        job: Job,
        state: JobState,
        journal: RunJournal,
        completion: Completion | None = None,
    ) -> None:
        self.config = config
        self.job = job
        self.state = state
        self.journal = journal
        self.completion = completion or request_completion
        self.trace: dict[str, Any] = {}

    def _event(self, kind: str, **fields: Any) -> dict[str, Any]:
        event = {
            "kind": kind,
            "job_id": self.job.job_id,
            "attempt": len(self.state.attempts),
            "at": datetime.now(UTC).isoformat(),
            **fields,
        }
        self.journal.append(event)
        return event

    def _request(self) -> dict[str, Any]:
        while True:
            last = self.state.last
            if last and last["status"] == "response":
                return last
            if last and last["status"] == "started":
                raise ValueError("Unresolved indeterminate HTTP attempt")
            cycle = 1
            delay = 0.0
            if last and last["status"] == "request_error":
                kind = last["error_type"]
                if (
                    kind not in self.config.retry.transient_errors
                    or last["cycle_attempt"] >= self.config.retry.max_attempts
                ):
                    return last
                delay = min(
                    self.config.retry.max_delay_seconds,
                    self.config.retry.initial_delay_seconds
                    * 2 ** (last["cycle_attempt"] - 1),
                )
                if delay:
                    time.sleep(delay)
                cycle = last["cycle_attempt"] + 1
            # Explicit indeterminate retry starts a fresh configured retry cycle.
            key = (
                os.environ.get(self.config.api_key_env)
                if self.config.api_key_env
                else None
            )
            if self.config.api_key_env and not key:
                raise ValueError(
                    "Configured credential environment variable is unset/empty"
                )
            number = len(self.state.attempts) + 1
            event = self._event(
                "started",
                attempt=number,
                cycle_attempt=cycle,
                backoff_before_seconds=delay,
                request=self.job.request,
                request_sha256=digest(self.job.request),
            )
            current = {**event, "status": "started"}
            self.state.attempts.append(current)
            start = time.perf_counter()
            try:
                response = self.completion(**self.job.request, api_key=key)
            except Exception as error:  # noqa: BLE001 # pylint: disable=broad-exception-caught
                if isinstance(error, TransportError):
                    kind = error.error_type
                    error_response = (
                        snapshot_response(error.response, key)
                        if error.response
                        else None
                    )
                elif isinstance(error, TimeoutError):
                    kind, error_response = EvaluationErrorType.API_TIMEOUT, None
                else:
                    kind, error_response = EvaluationErrorType.API_ERROR, None
                event = self._event(
                    "request_error",
                    error_type=kind.value,
                    error_response=error_response,
                    elapsed_seconds=time.perf_counter() - start,
                    # Provider exception messages/headers can contain credentials.
                    error=f"Request failed ({kind.value}; {type(error).__name__})",
                )
                current.update(event)
                current["status"] = "request_error"
                continue
            # Persist outside the exception handler: a storage error is never an
            # API error and must stop execution before any further HTTP request.
            raw = snapshot_response(response, key)
            event = self._event(
                "response",
                response=raw,
                response_sha256=digest(raw),
                elapsed_seconds=time.perf_counter() - start,
            )
            current.update(event)
            current["status"] = "response"
            return current

    def extract_with_metadata[T: BaseModel](  # pylint: disable=too-many-locals
        self, prompt: str, response_model: type[T]
    ) -> ExtractionResult[T]:
        request = self.job.request
        body = request["body"]
        if (
            body["messages"] != [{"role": "user", "content": prompt}]
            or body["response_format"]["json_schema"]["schema"]
            != response_model.model_json_schema()
        ):
            raise ValueError("Actual strategy request differs from preflight")
        last = self._request()
        elapsed = sum(
            attempt.get("elapsed_seconds", 0) + attempt.get("backoff_before_seconds", 0)
            for attempt in self.state.attempts
        )
        raw = last.get("response") or last.get("error_response")
        metadata = (
            extract_usage_metadata(raw, elapsed)
            if raw
            else ExtractionMetadata(
                latency_seconds=elapsed, llm_latency_seconds=elapsed
            )
        )
        metadata.request_attempts = len(self.state.attempts)
        if any(
            attempt["status"] == "indeterminate_retry"
            for attempt in self.state.attempts
        ):
            metadata.latency_seconds = metadata.llm_latency_seconds = None
        self.trace = {
            "job_id": self.job.job_id,
            "request": request,
            "request_sha256": digest(request),
            "response": raw,
            "response_sha256": last.get("response_sha256"),
            "request_id": raw.get("request_id") if raw else None,
            "response_id": raw.get("id") if raw else None,
            "confirmed_settings": None,
            "model_profile": {
                "user_supplied": self.job.model.expected_profile.model_dump(),
                "observed": observed_profile(raw or {}),
                "unverified_profile_fields": list(
                    type(self.job.model.expected_profile).model_fields
                ),
            },
            "attempts": self.state.attempts,
        }
        if last["status"] == "request_error":
            raise ExtractorError(
                last["error"],
                error_type=EvaluationErrorType(last["error_type"]),
                stage=EvaluationErrorStage.REQUEST,
                metadata=metadata,
            )
        assert raw is not None
        actual = observed_profile(raw)
        expected_profile = self.job.model.expected_profile.model_dump()
        mismatch = any(
            value is not None and actual.get(key) is not None and actual[key] != value
            for key, value in expected_profile.items()
            if key != "served_model_id"
        )
        # Reject observed drift, including across resumes and automatic retries.
        # Unknown values remain unknown rather than being inferred from aliases.
        selected_ids = {
            event["job_id"]
            for event in self.journal.events
            if event["kind"] == "started"
            and event["request"]["body"]["model"] == self.job.model.model_id
        }
        for event in self.journal.events:
            if event["kind"] == "response" and event["job_id"] in selected_ids:
                previous = observed_profile(event["response"])
                mismatch = mismatch or any(
                    value is not None
                    and actual.get(key) is not None
                    and actual[key] != value
                    for key, value in previous.items()
                )
        expected = self.job.model.expected_profile.served_model_id
        if mismatch or (expected is not None and raw.get("model") != expected):
            raise ExtractorError(
                "Served model ID does not match the expected profile",
                metadata=metadata,
                error_type=EvaluationErrorType.MODEL_PROFILE_MISMATCH,
                stage=EvaluationErrorStage.RESPONSE,
            )
        return parse_response(raw, response_model, metadata)
