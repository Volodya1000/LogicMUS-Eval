"""Strict, secret-free release and operator-evidence schemas."""

from typing import Literal, Self

from pydantic import Field, model_validator

from logicmus_eval.runner.config import StrictModel

TRANSPORT_CONTEXT_FAILURES = frozenset(
    {
        "context_error",
        "model_profile_mismatch",
        "api_error",
        "api_timeout",
        "api_connection",
    }
)


class ReleaseSpec(StrictModel):
    release_version: Literal["confirmation-release-v1"]
    release_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    plan: str
    protocol: str
    analysis_template: str
    configs: dict[str, str] = Field(min_length=1)
    development_plans: list[str] = Field(min_length=1)
    smoke_plan: str
    smoke_selection_rule: str | None = None
    supporting_files: list[str] = Field(default_factory=list)


class BackendEvidence(StrictModel):
    """Operator assertion backed by saved files; never described as server echo."""

    config_sha256: str
    checked_by: str = Field(min_length=1)
    checked_at: str = Field(min_length=1)
    method: str = Field(min_length=1)
    artifacts: dict[str, str] = Field(min_length=1)
    requests_sha256: str
    max_input_tokens: int = Field(gt=0)
    tokenizer_and_chat_template_verified: Literal[True]
    generation_and_timeout_verified: Literal[True]
    development_calibration_run: str


class SmokeEvidence(StrictModel):
    """Real execution requires explicit operator attestation plus verified journal."""

    evidence_version: Literal["development-smoke-v1", "infrastructure-smoke-v1"] = (
        "development-smoke-v1"
    )
    run_dir: str
    attested_real_http: Literal[True]
    checked_by: str = Field(min_length=1)
    checked_at: str = Field(min_length=1)
    resume_before_report: str
    resume_after_report: str
    analysis_dir: str
    longest_input_accounting: str
    artifacts: dict[str, str] = Field(min_length=1)
    parent_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    selection_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def check_infrastructure_identity(self) -> Self:
        if self.evidence_version == "infrastructure-smoke-v1" and (
            self.parent_manifest_sha256 is None or self.selection_sha256 is None
        ):
            raise ValueError(
                "Infrastructure evidence requires parent and selection hashes"
            )
        if self.evidence_version == "development-smoke-v1" and (
            self.parent_manifest_sha256 is not None or self.selection_sha256 is not None
        ):
            raise ValueError(
                "Parent/selection hashes require infrastructure evidence version"
            )
        return self


class InputTokenMeasurement(StrictModel):
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_tokens: int = Field(gt=0)


class ModelInputAccounting(StrictModel):
    model_id: str = Field(min_length=1)
    strategy: Literal["direct", "z3"]
    tokenizer: str = Field(min_length=1)
    chat_template: str = Field(min_length=1)
    target: list[InputTokenMeasurement] = Field(min_length=1)
    smoke: list[InputTokenMeasurement] = Field(min_length=1)


class InfrastructureInputAccounting(StrictModel):
    accounting_version: Literal["infrastructure-input-accounting-v1"]
    target_requests_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    smoke_requests_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    measurements: list[ModelInputAccounting] = Field(min_length=1)
