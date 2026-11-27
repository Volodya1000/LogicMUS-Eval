import logging
import time
from typing import TypeVar

import litellm
from pydantic import BaseModel
from tenacity import (
    AttemptManager,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from logicmus_eval.enums import EvaluationErrorStage, EvaluationErrorType
from logicmus_eval.errors import ExtractorError
from logicmus_eval.extractor_metadata import extract_usage_metadata
from logicmus_eval.models.evaluation import ExtractionMetadata
from logicmus_eval.models.extraction import ExtractionResult
from logicmus_eval.response_processing import parse_response

T = TypeVar("T", bound=BaseModel)
TRANSIENT_API_ERRORS: tuple[type[Exception], ...] = (
    litellm.exceptions.Timeout,
    litellm.exceptions.APIConnectionError,
    litellm.exceptions.RateLimitError,
)


__all__: list[str] = ["ExtractionResult", "ExtractorError", "StructuredOutputExtractor"]


class StructuredOutputExtractor:
    def __init__(self, model_name: str) -> None:
        self.model_name: str = model_name
        self.logger: logging.Logger = logging.getLogger(self.__class__.__name__)

    # Request and response phases share one timing/metadata boundary.
    # pylint: disable=too-many-locals
    def extract_with_metadata(
        self, prompt: str, response_model: type[T]
    ) -> ExtractionResult[T]:
        start_time: float = time.perf_counter()
        attempts: int = 0
        attempt: AttemptManager
        metadata: ExtractionMetadata
        kind: EvaluationErrorType
        exc: Exception
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
        metadata = extract_usage_metadata(response, time.perf_counter() - start_time)
        metadata.request_attempts = attempts
        return parse_response(response, response_model, metadata)

    def extract(self, prompt: str, response_model: type[T]) -> T:
        return self.extract_with_metadata(prompt, response_model).data
