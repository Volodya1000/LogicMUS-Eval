"""Pure production request serialization shared by preflight and input accounting."""

from typing import Any

from logicmus_eval.evaluation.strategies import (
    DirectEvaluationStrategy,
    Z3TranslationEvaluationStrategy,
)
from logicmus_eval.models.llm import DirectReasoningResponse, LLMToZ3Response
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.runner.config import ModelConfig, RunConfig


def build_request(
    config: RunConfig, model: ModelConfig, strategy: str, case: LogicTestCase
) -> dict[str, Any]:
    evaluator = (
        DirectEvaluationStrategy()
        if strategy == "direct"
        else Z3TranslationEvaluationStrategy()
    )
    schema = DirectReasoningResponse if strategy == "direct" else LLMToZ3Response
    return {
        "url": config.endpoint.rstrip("/") + "/chat/completions",
        "body": {
            "model": model.model_id,
            "messages": [{"role": "user", "content": evaluator.build_prompt(case)}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                },
            },
            **model.generation.model_dump(exclude_none=True),
            "stream": False,
        },
        "timeout": config.request_timeout_seconds,
        "transport": {
            "automatic_retries": 0,
            "follow_redirects": False,
            "environment_proxies": False,
        },
    }
