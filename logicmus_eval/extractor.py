import json
import logging
import time
from typing import TypeVar

import litellm
from pydantic import BaseModel, ValidationError
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from logicmus_eval.enums import EvaluationErrorStage, EvaluationErrorType
from logicmus_eval.evaluation.diagnostics import is_refusal
from logicmus_eval.models.evaluation import ExtractionMetadata

T = TypeVar("T", bound=BaseModel)
TRANSIENT_API_ERRORS = (
    litellm.exceptions.Timeout,
    litellm.exceptions.APIConnectionError,
    litellm.exceptions.RateLimitError,
)


class ExtractorError(Exception):
    """An expected request/response failure, with all observed diagnostics."""

    # Each keyword preserves a distinct observed request/response diagnostic.
    # pylint: disable=too-many-arguments
    def __init__(
        self,
        message: str,
        *,
        error_type: EvaluationErrorType = EvaluationErrorType.EXTRACTION_ERROR,
        stage: EvaluationErrorStage = EvaluationErrorStage.EXTRACTION,
        metadata: ExtractionMetadata | None = None,
        raw_response: str | None = None,
        refusal: bool = False,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.stage = stage
        self.metadata = metadata if metadata is not None else ExtractionMetadata()
        self.raw_response = raw_response
        self.refusal = refusal


class ExtractionResult[T: BaseModel](BaseModel):
    data: T
    metadata: ExtractionMetadata
    raw_response: str | None = None


def _field(obj: object, name: str) -> object:
    value: object = obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)
    return value


def _token_count(value: object) -> int | None:
    # A provider may omit any field independently; mocks/invalid metadata are
    # not measurements. In particular, preserve an explicitly reported zero.
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else None
    )


def _extract_usage_metadata(
    response: object, elapsed_time: float
) -> ExtractionMetadata:
    usage = _field(response, "usage")
    details = _field(usage, "completion_tokens_details")
    return ExtractionMetadata(
        latency_seconds=elapsed_time,
        llm_latency_seconds=elapsed_time,
        prompt_tokens=_token_count(_field(usage, "prompt_tokens")),
        completion_tokens=_token_count(_field(usage, "completion_tokens")),
        thinking_tokens=_token_count(_field(details, "reasoning_tokens")),
        total_tokens=_token_count(_field(usage, "total_tokens")),
    )


class StructuredOutputExtractor:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.logger = logging.getLogger(self.__class__.__name__)

    # Request and response phases share one timing/metadata boundary.
    # pylint: disable=too-many-locals
    def extract_with_metadata(
        self, prompt: str, response_model: type[T]
    ) -> ExtractionResult[T]:
        start_time = time.perf_counter()
        attempts = 0
        try:
            for attempt in Retrying(
                stop=stop_after_attempt(3),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                retry=retry_if_exception_type(TRANSIENT_API_ERRORS),
                reraise=True,
            ):
                with attempt:
                    attempts += 1
                    self.logger.info("Sending request to model: %s", self.model_name)
                    response: object = litellm.completion(
                        model=self.model_name,
                        messages=[{"role": "user", "content": prompt}],
                        response_format=response_model,
                        temperature=0.0,
                        timeout=120,
                        max_retries=0,
                    )
        except TRANSIENT_API_ERRORS as exc:
            metadata = ExtractionMetadata(
                latency_seconds=time.perf_counter() - start_time,
                request_attempts=attempts,
            )
            metadata.llm_latency_seconds = metadata.latency_seconds
            if isinstance(exc, litellm.exceptions.Timeout):
                kind = EvaluationErrorType.API_TIMEOUT
            elif isinstance(exc, litellm.exceptions.RateLimitError):
                kind = EvaluationErrorType.API_RATE_LIMIT
            else:
                kind = EvaluationErrorType.API_CONNECTION
            raise ExtractorError(
                str(exc),
                error_type=kind,
                stage=EvaluationErrorStage.REQUEST,
                metadata=metadata,
            ) from exc

        # Capture observed cost and end-to-end request latency (including retry
        # waits) before any response access, JSON parsing or schema validation.
        metadata = _extract_usage_metadata(response, time.perf_counter() - start_time)
        metadata.request_attempts = attempts
        choices = _field(response, "choices")
        message = (
            _field(choices[0], "message")
            if isinstance(choices, (list, tuple)) and choices
            else None
        )
        content = _field(message, "content")
        self.logger.info("RAW LLM OUTPUT:\n%s", content)
        refusal = _field(message, "refusal")
        if isinstance(refusal, str) and refusal:
            raise ExtractorError(
                refusal,
                error_type=EvaluationErrorType.REFUSAL,
                stage=EvaluationErrorStage.RESPONSE,
                metadata=metadata,
                raw_response=content
                if isinstance(content, str) and content
                else refusal,
            )
        if (
            content is None
            or content == ""
            or (isinstance(content, str) and not content.strip())
        ):
            raise ExtractorError(
                "Empty response from LLM",
                error_type=EvaluationErrorType.EMPTY_RESPONSE,
                stage=EvaluationErrorStage.RESPONSE,
                metadata=metadata,
                raw_response=content if isinstance(content, str) else None,
            )
        if not isinstance(content, str):
            raise ExtractorError(
                "Response content must be text",
                error_type=EvaluationErrorType.SCHEMA_ERROR,
                stage=EvaluationErrorStage.SCHEMA,
                metadata=metadata,
                raw_response=repr(content),
            )
        try:
            data: object = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ExtractorError(
                f"Failed to parse JSON: {exc}",
                error_type=EvaluationErrorType.JSON_ERROR,
                stage=EvaluationErrorStage.PARSE,
                metadata=metadata,
                raw_response=content,
                # Inspect only unstructured prose, never JSON/code payloads.
                refusal=not content.lstrip().startswith(("{", "[", "```"))
                and is_refusal(content),
            ) from exc
        try:
            parsed_response = response_model.model_validate(data, strict=True)
        except ValidationError as exc:
            raise ExtractorError(
                f"Response schema validation failed: {exc}",
                error_type=EvaluationErrorType.SCHEMA_ERROR,
                stage=EvaluationErrorStage.SCHEMA,
                metadata=metadata,
                raw_response=content,
            ) from exc
        return ExtractionResult(
            data=parsed_response, metadata=metadata, raw_response=content
        )

    def extract(self, prompt: str, response_model: type[T]) -> T:
        return self.extract_with_metadata(prompt, response_model).data
