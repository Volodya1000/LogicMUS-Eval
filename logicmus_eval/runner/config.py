"""Explicit, secret-free inference contract, independent of generation plans."""

from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class GenerationConfig(StrictModel):
    max_tokens: int = Field(gt=0)
    temperature: float = Field(ge=0)
    top_p: float | None = Field(default=None, gt=0, le=1)
    seed: int | None = None
    reasoning_effort: Literal["none", "minimal", "low", "medium", "high"] | None = None


class ModelProfile(StrictModel):
    """All fields here are user assertions, never inferred from an alias."""

    served_model_id: str | None = None
    revision: str | None = None
    model_file: str | None = None
    quantization: str | None = None
    context_tokens: int | None = Field(default=None, gt=0)
    backend_version: str | None = None
    chat_template: str | None = None
    tokenizer: str | None = None


class ModelConfig(StrictModel):
    model_id: str = Field(min_length=1)
    expected_profile: ModelProfile
    generation: GenerationConfig

    @model_validator(mode="after")
    def check_context(self) -> Self:
        context = self.expected_profile.context_tokens
        if context is not None and self.generation.max_tokens >= context:
            raise ValueError("Output budget leaves no input context")
        return self


class RetryConfig(StrictModel):
    max_attempts: int = Field(ge=1)
    initial_delay_seconds: float = Field(ge=0)
    max_delay_seconds: float = Field(ge=0)
    transient_errors: list[
        Literal["api_timeout", "api_connection", "api_rate_limit", "api_unavailable"]
    ]

    @model_validator(mode="after")
    def check_retry(self) -> Self:
        if self.max_delay_seconds < self.initial_delay_seconds:
            raise ValueError("max_delay_seconds must cover initial_delay_seconds")
        if len(set(self.transient_errors)) != len(self.transient_errors):
            raise ValueError("Duplicate transient error")
        return self


class RunConfig(StrictModel):
    config_version: Literal["controlled-run-v1"]
    series_manifest: str
    endpoint: str
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    models: list[ModelConfig] = Field(min_length=1)
    strategies: list[Literal["direct", "z3"]] = Field(min_length=1)
    request_timeout_seconds: float = Field(gt=0)
    retry: RetryConfig
    z3_timeout_seconds: float = Field(gt=0)
    diagnostic_parent_run: str | None = None

    @model_validator(mode="after")
    def check_selection(self) -> Self:
        ids = [model.model_id for model in self.models]
        if len(set(ids)) != len(ids) or len(set(self.strategies)) != len(
            self.strategies
        ):
            raise ValueError("Duplicate model or strategy")
        endpoint = urlsplit(self.endpoint)
        if (
            endpoint.scheme not in {"http", "https"}
            or not endpoint.hostname
            or any(
                (
                    endpoint.username,
                    endpoint.password,
                    endpoint.query,
                    endpoint.fragment,
                )
            )
        ):
            raise ValueError(
                "endpoint must be an HTTP(S) URL without credentials/query/fragment"
            )
        return self


def load_config(path: Path) -> RunConfig:
    config = RunConfig.model_validate_json(path.read_text(encoding="utf-8"))
    manifest = Path(config.series_manifest)
    if not manifest.is_absolute():
        config.series_manifest = str((path.parent / manifest).resolve())
    return config
