"""Typed parsed model response and observed request metadata."""

from typing import Protocol

from pydantic import BaseModel

from logicmus_eval.models.evaluation import ExtractionMetadata


class ExtractionResult[T: BaseModel](BaseModel):
    data: T
    metadata: ExtractionMetadata
    raw_response: str | None = None


class ExtractionClient(Protocol):
    def extract_with_metadata[T: BaseModel](
        self, prompt: str, response_model: type[T]
    ) -> ExtractionResult[T]: ...
