from typing import Any

from pydantic import BaseModel, Field


class ExtractionMetadata(BaseModel):
    latency_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    thinking_tokens: int = 0
    total_tokens: int = 0


class CasePrediction(BaseModel):
    is_sat: bool | None = None
    conflict_core: list[str] = Field(default_factory=list)
    reasoning: str = ""
    generated_code: str | None = None
    execution_success: bool = True
    error: str | None = None


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


class EvaluationSummary(BaseModel):
    metrics: dict[str, Any]
    details: list[EvaluationCaseReport]
