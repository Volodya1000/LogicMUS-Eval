"""Strict, secret-free release and operator-evidence schemas."""

from typing import Literal

from pydantic import Field

from logicmus_eval.runner.config import StrictModel


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

    run_dir: str
    attested_real_http: Literal[True]
    checked_by: str = Field(min_length=1)
    checked_at: str = Field(min_length=1)
    resume_before_report: str
    resume_after_report: str
    analysis_dir: str
    longest_input_accounting: str
    artifacts: dict[str, str] = Field(min_length=1)
