import json
import logging
import time
from typing import Any, Generic, TypeVar

import litellm  # type: ignore
from pydantic import BaseModel
from tenacity import (  # type: ignore
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from logicmus_eval.models.evaluation import ExtractionMetadata

T = TypeVar("T", bound=BaseModel)


class ExtractorError(Exception):
    pass


class ExtractionResult(BaseModel, Generic[T]):  # noqa: UP046
    data: T
    metadata: ExtractionMetadata


def _extract_usage_metadata(response: Any, elapsed_time: float) -> ExtractionMetadata:
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
    total_tokens = getattr(usage, "total_tokens", 0) or 0

    thinking_tokens = 0
    details = getattr(usage, "completion_tokens_details", None)
    if details:
        if isinstance(details, dict):
            thinking_tokens = details.get("reasoning_tokens", 0) or 0
        else:
            thinking_tokens = getattr(details, "reasoning_tokens", 0) or 0

    return ExtractionMetadata(
        latency_seconds=elapsed_time,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        thinking_tokens=thinking_tokens,
        total_tokens=total_tokens,
    )


class StructuredOutputExtractor:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.logger = logging.getLogger(self.__class__.__name__)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(
            (
                litellm.exceptions.APIConnectionError,
                litellm.exceptions.RateLimitError,
                litellm.exceptions.Timeout,
            )
        ),
        reraise=True,
    )
    def extract_with_metadata(
        self, prompt: str, response_model: type[T]
    ) -> ExtractionResult[T]:
        start_time = time.perf_counter()
        content = ""
        try:
            self.logger.info("Sending request to model: %s", self.model_name)
            response = litellm.completion(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format=response_model,
                temperature=0.0,
            )
            elapsed_time = time.perf_counter() - start_time

            content = response.choices[0].message.content
            self.logger.info("RAW LLM OUTPUT:\n%s", content)

            if not content:
                raise ExtractorError("Empty response from LLM")

            data = json.loads(content)
            parsed_response = response_model.model_validate(data)

            metadata = _extract_usage_metadata(response, elapsed_time)

            return ExtractionResult(data=parsed_response, metadata=metadata)

        except json.JSONDecodeError as e:
            self.logger.error("JSON Decode Error: %s", str(e))
            raise ExtractorError(f"Failed to parse JSON: {e}\nRaw: {content}") from e
        except Exception as e:
            if isinstance(e, ExtractorError):
                raise
            self.logger.error("Extraction error: %s", str(e))
            raise

    def extract(self, prompt: str, response_model: type[T]) -> T:
        return self.extract_with_metadata(prompt, response_model).data
