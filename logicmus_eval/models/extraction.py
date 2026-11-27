"""Typed parsed model response and observed request metadata."""

from pydantic import BaseModel

from logicmus_eval.models.evaluation import ExtractionMetadata


class ExtractionResult[T: BaseModel](BaseModel):
    data: T
    metadata: ExtractionMetadata
    raw_response: str | None = None
