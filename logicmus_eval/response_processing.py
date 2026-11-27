"""Pure response parsing, shared by live extraction and durable response replay."""

import json

from pydantic import BaseModel, ValidationError

from logicmus_eval.enums import EvaluationErrorStage, EvaluationErrorType
from logicmus_eval.errors import ExtractorError
from logicmus_eval.evaluation.diagnostics import is_refusal
from logicmus_eval.extractor_metadata import response_field
from logicmus_eval.models.evaluation import ExtractionMetadata
from logicmus_eval.models.extraction import ExtractionResult


def parse_response[T: BaseModel](
    response: object, response_model: type[T], metadata: ExtractionMetadata
) -> ExtractionResult[T]:
    if response_field(response, "body_json_error") is True:
        raw_body = response_field(response, "raw_body")
        raise ExtractorError(
            "HTTP response body is not a JSON object",
            error_type=EvaluationErrorType.JSON_ERROR,
            stage=EvaluationErrorStage.PARSE,
            metadata=metadata,
            raw_response=raw_body if isinstance(raw_body, str) else None,
        )
    choices: object = response_field(response, "choices")
    message: object = (
        response_field(choices[0], "message")
        if isinstance(choices, (list, tuple)) and choices
        else None
    )
    content: object = response_field(message, "content")
    if metadata.finish_reason == "length":
        raise ExtractorError(
            "Generation reached output token limit",
            error_type=EvaluationErrorType.GENERATION_TRUNCATED,
            stage=EvaluationErrorStage.RESPONSE,
            metadata=metadata,
            raw_response=content if isinstance(content, str) else None,
        )
    refusal: object = response_field(message, "refusal")
    if isinstance(refusal, str) and refusal:
        raise ExtractorError(
            refusal,
            error_type=EvaluationErrorType.REFUSAL,
            stage=EvaluationErrorStage.RESPONSE,
            metadata=metadata,
            raw_response=content if isinstance(content, str) and content else refusal,
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
        parsed_response: T = response_model.model_validate(data, strict=True)
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
