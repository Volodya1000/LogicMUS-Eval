"""Two real local-LLM requests through the production extractor/strategy/pipeline.

Only request time/token limits and logging are instrumented. The completion
function delegates to the real LiteLLM HTTP client and never supplies responses.
Run from the repository root: python docs/validation/2026-11-27-lmstudio-z3/smoke.py
"""

import hashlib
import json
import os
import subprocess
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import litellm
from pydantic import BaseModel

from logicmus_eval.enums import (
    EvaluationErrorStage,
    EvaluationErrorType,
    TemplatePackId,
)
from logicmus_eval.errors import ExtractorError
from logicmus_eval.evaluate_llm import _build_metrics
from logicmus_eval.evaluation.pipeline import EvaluationPipeline
from logicmus_eval.evaluation.strategies import Z3TranslationEvaluationStrategy
from logicmus_eval.extractor import StructuredOutputExtractor
from logicmus_eval.models.evaluation import EvaluationSummary
from logicmus_eval.models.test_case import LogicTestCase

OUTPUT: Path = Path(__file__).resolve().parent
REPOSITORY: Path = Path(__file__).resolve().parents[3]
MODEL: str = "openai/qwen2.5-coder-14b-instruct"
BUDGET_SECONDS: float = 40.0


def build_cases() -> list[LogicTestCase]:
    rules: list[dict[str, str]] = [
        {
            "id": "R1",
            "text": "Датчик включен.",
            "variable": "x",
            "operator_type": "FACT",
        },
        {
            "id": "R2",
            "text": "Если датчик включен, лампа горит.",
            "antecedent": "x",
            "consequent": "y",
            "operator_type": "IMPLIES",
        },
    ]
    return [
        LogicTestCase(
            case_id="live-sat",
            mus_size=2,
            is_satisfiable=True,
            template_pack_id=TemplatePackId.PACK_00,
            predicate_mapping={"x": "Датчик включен", "y": "Лампа горит"},
            rules=[
                *rules,
                {
                    "id": "R3",
                    "text": "Лампа горит.",
                    "variable": "y",
                    "operator_type": "FACT",
                },
            ],
            mus_expected=[],
        ),
        LogicTestCase(
            case_id="live-unsat",
            mus_size=3,
            is_satisfiable=False,
            template_pack_id=TemplatePackId.PACK_00,
            predicate_mapping={"x": "Датчик включен", "y": "Лампа горит"},
            rules=[
                *rules,
                {
                    "id": "R3",
                    "text": "Лампа не горит.",
                    "variable": "Not(y)",
                    "operator_type": "TERMINAL",
                },
            ],
            mus_expected=["R1", "R2", "R3"],
        ),
    ]


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    os.environ["OPENAI_API_BASE"] = "http://127.0.0.1:1234/v1"
    os.environ["OPENAI_API_KEY"] = "lm-studio"
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    original_completion: Callable[..., Any] = litellm.completion
    requests: list[dict[str, Any]] = []
    cases: list[LogicTestCase] = build_cases()
    strategy: Z3TranslationEvaluationStrategy = Z3TranslationEvaluationStrategy()
    source_paths: list[Path] = sorted((REPOSITORY / "logicmus_eval").rglob("*.py"))
    digest: Any = hashlib.sha256()
    source_path: Path
    for source_path in source_paths:
        digest.update(source_path.relative_to(REPOSITORY).as_posix().encode("utf-8"))
        digest.update(source_path.read_bytes())
    record: dict[str, Any] = {
        "started_at_utc": datetime.now(UTC).isoformat(),
        "endpoint": os.environ["OPENAI_API_BASE"],
        "model": MODEL,
        "budget_seconds": BUDGET_SECONDS,
        "instrumentation": (
            "Real LiteLLM calls; timeout capped by remaining budget; "
            "max_tokens=768; no fabricated responses or code repair"
        ),
        "git_base_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPOSITORY, text=True
        ).strip(),
        "production_source_sha256": digest.hexdigest(),
        "cases": [case.model_dump(mode="json") for case in cases],
        "prompts": [strategy.build_prompt(case) for case in cases],
        "requests": requests,
    }
    started: float = time.monotonic()
    deadline: float = started + BUDGET_SECONDS

    def observed_completion(*args: Any, **kwargs: Any) -> Any:
        remaining: float = deadline - time.monotonic()
        if remaining <= 0:
            raise ExtractorError(
                "Live smoke wall-clock budget exhausted",
                error_type=EvaluationErrorType.API_TIMEOUT,
                stage=EvaluationErrorStage.REQUEST,
            )
        kwargs["timeout"] = remaining
        kwargs["max_tokens"] = 768
        request: dict[str, Any] = {
            "started_after_seconds": time.monotonic() - started,
            "model": kwargs["model"],
            "messages": kwargs["messages"],
            "timeout": remaining,
            "max_tokens": 768,
            "temperature": kwargs["temperature"],
            "max_retries": kwargs["max_retries"],
        }
        requests.append(request)
        write_json(OUTPUT / "trace.json", record)
        result: Any = original_completion(*args, **kwargs)
        request["finished_after_seconds"] = time.monotonic() - started
        request["response"] = (
            result.model_dump(mode="json")
            if isinstance(result, BaseModel)
            else repr(result)
        )
        write_json(OUTPUT / "trace.json", record)
        return result

    # Transparent instrumentation of actual networking, not an offline mock.
    litellm.completion = observed_completion
    try:
        pipeline: EvaluationPipeline = EvaluationPipeline(
            strategy, StructuredOutputExtractor(MODEL), _build_metrics()
        )
        report: EvaluationSummary = pipeline.run(
            cases, output_path=OUTPUT / "report.json"
        )
        record["elapsed_seconds"] = time.monotonic() - started
        record["finished_at_utc"] = datetime.now(UTC).isoformat()
        record["report"] = report.model_dump(mode="json")
        write_json(OUTPUT / "trace.json", record)
        print(
            json.dumps(
                {
                    "elapsed_seconds": record["elapsed_seconds"],
                    "requests": len(requests),
                    "cases": [
                        {
                            "id": detail.case_id,
                            "valid_response": detail.valid_response,
                            "predicted_sat": detail.predicted_sat,
                            "core": detail.predicted_mus,
                            "sat_correct": detail.is_sat_correct,
                            "mus_correct": detail.is_mus_correct,
                            "error": detail.error,
                            "code": detail.generated_code,
                        }
                        for detail in report.details
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    finally:
        litellm.completion = original_completion


if __name__ == "__main__":
    main()
