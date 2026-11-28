"""Validated saved-run contracts, independent of inference and current sources."""

from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    model_validator,
)

from logicmus_eval.infrastructure_smoke import InfrastructureSelection
from logicmus_eval.models.evaluation import EvaluationCaseReport
from logicmus_eval.runner.config import (
    GenerationConfig,
    ModelProfile,
    RunConfig,
    StrictModel,
)

Strategy = Literal["direct", "z3"]


class SavedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    def saved_json(self) -> dict[str, JsonValue]:
        """Preserve absent optional keys and aliases when checking original hashes."""
        return JSON_OBJECT.validate_python(
            self.model_dump(mode="json", by_alias=True, exclude_unset=True)
        )


JSON_OBJECT = TypeAdapter(dict[str, JsonValue])


class InventoryJob(SavedModel):
    job_id: str
    case_uid: str
    cell_id: str
    request_sha256: str


class SavedJob(InventoryJob):
    model_id: str
    strategy: Strategy


class RuntimeVersions(SavedModel):
    python: str
    pydantic: str
    z3_solver: str = Field(alias="z3-solver")


class SavedIdentity(SavedModel):
    runner_protocol: str
    transport_protocol: str
    config: RunConfig
    series_manifest_sha256: str
    plan_sha256: str
    source_bundle_sha256: str
    report_schema_version: int
    metric_definitions_version: str
    z3_execution_protocol_version: str
    runtime: RuntimeVersions
    requests_sha256: str
    generation_protocol: Literal["controlled-v1", "controlled-v2"] | None = None
    smoke_selection: InfrastructureSelection | None = None

    @model_validator(mode="after")
    def smoke_scope(self) -> Self:
        configured = self.config.infrastructure_smoke
        selected = self.smoke_selection
        scopes = (
            self.runner_protocol == "infrastructure-smoke-v1",
            configured is not None,
            selected is not None,
        )
        if any(scopes) and not all(scopes):
            raise ValueError(
                "Smoke identity requires matching protocol, config and selection"
            )
        if (
            configured is not None
            and selected is not None
            and not all(
                (
                    configured.selection_sha256 == selected.selection_sha256,
                    self.series_manifest_sha256 == selected.parent_manifest_sha256,
                    self.plan_sha256 == selected.parent_plan_sha256,
                    self.generation_protocol is not None,
                )
            )
        ):
            raise ValueError("Smoke identity differs from pinned parent/selection")
        return self


class SavedPayload(SavedModel):
    run_id: str
    created_at: str
    identity: SavedIdentity
    job_ids: list[str]
    jobs: list[SavedJob]


class SavedManifest(SavedModel):
    payload: SavedPayload
    manifest_sha256: str


class RequestMessage(SavedModel):
    role: Literal["user"]
    content: str


class ResponseSchema(SavedModel):
    name: str
    schema_definition: dict[str, JsonValue] = Field(alias="schema")


class ResponseFormat(SavedModel):
    type: Literal["json_schema"]
    json_schema: ResponseSchema


class RequestBody(GenerationConfig):
    model: str
    messages: list[RequestMessage]
    response_format: ResponseFormat
    stream: Literal[False]


class RequestTransport(SavedModel):
    automatic_retries: Literal[0]
    follow_redirects: Literal[False]
    environment_proxies: Literal[False]


class SavedRequest(SavedModel):
    url: str
    body: RequestBody
    timeout: float
    transport: RequestTransport


class ObservedProfile(ModelProfile):
    model_id: str | None = None
    system_fingerprint: str | None = None


class TraceProfile(StrictModel):
    user_supplied: ModelProfile
    observed: ObservedProfile
    unverified_profile_fields: list[str]


class TraceIdentity(BaseModel):
    """Only the trace fields consumed by analysis; opaque provider data stay JSON."""

    model_config = ConfigDict(strict=True)
    job_id: str
    request_sha256: str
    model_profile: TraceProfile


class RunnerProvenance(SavedModel):
    protocol: str
    run_id: str
    manifest_sha256: str
    identity_sha256: str
    source_bundle_sha256: str
    journal_head_sha256: str
    journal_event_count: int
    finalized: int
    planned: int
    pending: int
    indeterminate: int
    responses_awaiting_processing: int
    indeterminate_attempts: int
    attempts_with_unknown_cost: int
    http_attempts: int
    model_id: str | None = None
    strategy: Strategy | None = None


class Event(SavedModel):
    job_id: str
    at: str


class StartedEvent(Event):
    kind: Literal["started"]
    attempt: int
    cycle_attempt: int
    backoff_before_seconds: float
    request: SavedRequest
    request_sha256: str
    invocation_origin: Literal["http-adapter", "injected-completion"] | None = None


class ResponseEvent(Event):
    kind: Literal["response"]
    attempt: int
    response: dict[str, JsonValue]
    response_sha256: str
    elapsed_seconds: float


class RequestErrorEvent(Event):
    kind: Literal["request_error"]
    attempt: int
    error_type: str
    error_response: dict[str, JsonValue] | None
    elapsed_seconds: float
    error: str


class RetryEvent(Event):
    kind: Literal["indeterminate_retry"]
    attempt: int
    policy: Literal["retry"]
    previous_request_may_have_been_processed: Literal[True]
    previous_cost: Literal["unknown"]


class FinalizedEvent(Event):
    kind: Literal["finalized"]
    outcome: EvaluationCaseReport


AttemptResult = ResponseEvent | RequestErrorEvent | RetryEvent
JournalEvent = Annotated[
    StartedEvent | AttemptResult | FinalizedEvent, Field(discriminator="kind")
]
JOURNAL_EVENTS = TypeAdapter(list[JournalEvent])
