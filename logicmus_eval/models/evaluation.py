from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ExtractionMetadata(BaseModel):
    latency_seconds: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    thinking_tokens: int | None = None
    total_tokens: int | None = None
    request_attempts: int | None = None


class CasePrediction(BaseModel):
    is_sat: bool | None = None
    conflict_core: list[str] = Field(default_factory=list)
    reasoning: str = ""
    generated_code: str | None = None
    execution_success: bool = True
    error: str | None = None
    error_type: str | None = None
    error_stage: str | None = None
    raw_response: str | None = None
    refusal: bool = False


class Z3ExecutionResult(BaseModel):
    success: bool
    is_sat: bool | None = None
    conflict_core: list[str] = Field(default_factory=list)
    error: str | None = None
    execution_time: float = 0.0


class EvaluationCaseReport(BaseModel):
    case_id: str
    mus_size: int
    expected_sat: bool
    predicted_sat: bool | None
    is_sat_correct: bool
    expected_mus: list[str]
    predicted_mus: list[str]
    is_mus_correct: bool
    metadata: ExtractionMetadata
    reasoning: str
    generated_code: str | None = None
    error: str | None = None
    failure_tags: list[str] = Field(default_factory=list)
    # None means not recorded by the historical report, not a new verdict.
    valid_response: bool | None = None
    refusal: bool | None = None
    error_type: str | None = None
    error_stage: str | None = None
    raw_response: str | None = None
    mus_precision: float | None = None
    mus_recall: float | None = None
    mus_f1: float | None = None


class RunInfo(BaseModel):
    model_name: str
    strategy: str
    dataset_filename: str
    dataset_sha256: str
    prompt_template_hash: str
    git_commit: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    limit: int | None = None
    total_cases_processed: int = 0


class EvaluationSummary(BaseModel):
    metrics: dict[str, Any]
    details: list[EvaluationCaseReport]
    run_info: RunInfo | None = None
    # Assigned by the new pipeline only; loading legacy JSON never upgrades it.
    report_schema_version: int | None = None
    metric_definitions_version: str | None = None
    status: Literal["running", "completed"] | None = None
