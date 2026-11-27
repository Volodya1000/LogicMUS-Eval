"""Pure access and usage-metadata normalization for provider responses."""

from logicmus_eval.models.evaluation import ExtractionMetadata


def response_field(obj: object, name: str) -> object:
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


def extract_usage_metadata(response: object, elapsed_time: float) -> ExtractionMetadata:
    usage: object = response_field(response, "usage")
    details: object = response_field(usage, "completion_tokens_details")
    choices = response_field(response, "choices")
    finish = (
        response_field(choices[0], "finish_reason")
        if isinstance(choices, (list, tuple)) and choices
        else None
    )
    return ExtractionMetadata(
        latency_seconds=elapsed_time,
        llm_latency_seconds=elapsed_time,
        prompt_tokens=_token_count(response_field(usage, "prompt_tokens")),
        completion_tokens=_token_count(response_field(usage, "completion_tokens")),
        thinking_tokens=_token_count(response_field(details, "reasoning_tokens")),
        total_tokens=_token_count(response_field(usage, "total_tokens")),
        finish_reason=finish if isinstance(finish, str) else None,
    )
