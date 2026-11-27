from collections.abc import Mapping
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError

from logicmus_eval.enums import (
    EvaluationErrorCategory,
    EvaluationErrorStage,
    EvaluationErrorType,
    EvaluationStatus,
)

REPORT_SCHEMA_VERSION: int = 3
METRIC_DEFINITIONS_VERSION: str = "3"
Z3_EXECUTION_PROTOCOL_VERSION: str = "1"
Purpose = Literal["development", "confirmation"]
SeriesKind = Literal["noise_sweep", "k_sweep", "topology_panel"]


class ExtractionMetadata(BaseModel):
    # Legacy alias for request time; never reinterpret old measurements as E2E.
    latency_seconds: float | None = None
    llm_latency_seconds: float | None = None
    case_latency_seconds: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    thinking_tokens: int | None = None
    total_tokens: int | None = None
    request_attempts: int | None = None
    finish_reason: str | None = None


class CasePrediction(BaseModel):
    is_sat: bool | None = None
    conflict_core: list[str] = Field(default_factory=list)
    reasoning: str = ""
    generated_code: str | None = None
    execution_success: bool = True
    error: str | None = None
    error_type: EvaluationErrorType | None = None
    error_stage: EvaluationErrorStage | None = None
    raw_response: str | None = None
    refusal: bool = False


class Z3ExecutionResult(BaseModel):
    success: bool
    is_sat: bool | None = None
    conflict_core: list[str] = Field(default_factory=list)
    error: str | None = None
    error_type: EvaluationErrorType | None = None
    diagnostics: str = ""
    execution_time: float = 0.0


class ExperimentProvenance(BaseModel):
    """Controlled experiment identifiers and counts recorded by the dataset."""

    model_config = ConfigDict(strict=True)

    protocol_version: Literal["controlled-v1"]
    cell_id: str
    family_id: str
    pair_id: str
    pattern_id: str
    purpose: Purpose
    series_id: str
    series_kind: SeriesKind
    seed: int
    pair_index: int
    total_rules: int
    construction_rule_count: int
    independent_noise_count: int
    case_uid: str

    @classmethod
    def from_case_metadata(cls, metadata: Mapping[str, object]) -> Self | None:
        """Return provenance only when the case records every required field."""
        try:
            return cls.model_validate(metadata)
        except ValidationError:
            return None


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
    experiment: ExperimentProvenance | None = None
    generated_code: str | None = None
    error: str | None = None
    failure_tags: list[str] = Field(default_factory=list)
    # None means not recorded by the historical report, not a new verdict.
    valid_response: bool | None = None
    refusal: bool | None = None
    error_type: EvaluationErrorType | None = None
    error_stage: EvaluationErrorStage | None = None
    error_category: EvaluationErrorCategory | None = None
    raw_response: str | None = None
    mus_precision: float | None = None
    mus_recall: float | None = None
    mus_f1: float | None = None
    inference: dict[str, JsonValue] | None = None


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
    metrics: dict[str, JsonValue]
    details: list[EvaluationCaseReport]
    run_info: RunInfo | None = None
    # Assigned by the new pipeline only; loading legacy JSON never upgrades it.
    report_schema_version: int | None = None
    metric_definitions_version: str | None = None
    z3_execution_protocol_version: str | None = None
    status: EvaluationStatus | None = None
    runner_provenance: dict[str, JsonValue] | None = None
