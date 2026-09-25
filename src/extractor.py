import json
import logging
from typing import TypeVar

import litellm  # type: ignore
from pydantic import BaseModel
from tenacity import (  # type: ignore
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

T = TypeVar("T", bound=BaseModel)


class ExtractorError(Exception):
    pass


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
                ExtractorError,
            )
        ),
        reraise=True,
    )
    def extract(self, prompt: str, response_model: type[T]) -> T:
        try:
            self.logger.info("Sending request to model: %s", self.model_name)
            response = litellm.completion(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                response_format=response_model,
                temperature=0.0,
            )

            content = response.choices[0].message.content

            self.logger.info("RAW LLM OUTPUT:\n%s", content)

            if not content:
                raise ExtractorError("Empty response from LLM")

            data = json.loads(content)
            parsed_response = response_model.model_validate(data)
            self.logger.info(
                "Successfully parsed response into %s", response_model.__name__
            )

            return parsed_response

        except json.JSONDecodeError as e:
            self.logger.error("JSON Decode Error. Raw content: %s", content)
            raise ExtractorError(f"Failed to parse JSON: {e}") from e
        except Exception as e:
            self.logger.error("Extraction failed: %s", str(e))
            if isinstance(e, ExtractorError):
                raise
            raise
