"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Mapping, Sequence

from pydantic import JsonValue

from logicmus_eval.enums import EvaluationErrorCategory
from logicmus_eval.evaluation.diagnostics import build_case_report
from logicmus_eval.models.evaluation import (
    CasePrediction,
    EvaluationCaseReport,
    ExtractionMetadata,
)
from logicmus_eval.models.test_case import LogicTestCase


def _ratio(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def accounting_counts(
    reports: Sequence[EvaluationCaseReport], planned: int
) -> dict[str, JsonValue]:
    """Each primary error counts a case once, independent of diagnostic tags."""
    errors = Counter(r.error_type for r in reports if r.error_type is not None)
    return {
        "planned": planned,
        "processed": len(reports),
        "valid_responses_evaluated": sum(r.valid_response is True for r in reports),
        "unsat_evaluated": sum(not r.expected_sat for r in reports),
        "correct_sat": sum(r.is_sat_correct for r in reports),
        "refusal_count": sum(r.refusal is True for r in reports),
        "error_count": sum(errors.values()),
        "error_counts": dict(sorted(errors.items())),
    }


class BaseMetric(ABC):
    def __init__(self) -> None:
        self.reports: list[EvaluationCaseReport] = []

    def update(
        self,
        case: LogicTestCase,
        prediction: CasePrediction,
        metadata: ExtractionMetadata,
    ) -> None:
        """Retain standalone callers; the pipeline finalizes the outcome only once."""
        self.update_report(build_case_report(case, prediction, metadata))

    def update_report(self, report: EvaluationCaseReport) -> None:
        self.reports.append(report)

    @abstractmethod
    def compute(self) -> Mapping[str, JsonValue]:
        pass

    def reset(self) -> None:
        self.reports.clear()


class SatAccuracyMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        correct = sum(r.is_sat_correct for r in self.reports)
        return {
            "sat_accuracy": _ratio(correct, len(self.reports)),
            "total_evaluated": len(self.reports),
            "correct_sat": correct,
        }


class MusValidMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        unsat = [r for r in self.reports if not r.expected_sat]
        return {
            "mus_exact_match": _ratio(sum(r.is_mus_correct for r in unsat), len(unsat)),
            "mus_precision": _ratio(
                sum(r.mus_precision or 0.0 for r in unsat), len(unsat)
            ),
            "mus_recall": _ratio(sum(r.mus_recall or 0.0 for r in unsat), len(unsat)),
            "mus_f1": _ratio(sum(r.mus_f1 or 0.0 for r in unsat), len(unsat)),
            "unsat_evaluated": len(unsat),
        }


class TokenUsageMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        values = {
            "prompt_tokens": [r.metadata.prompt_tokens for r in self.reports],
            "completion_tokens": [r.metadata.completion_tokens for r in self.reports],
            "thinking_tokens": [r.metadata.thinking_tokens for r in self.reports],
            "total_tokens": [r.metadata.total_tokens for r in self.reports],
        }
        known = {
            name: [v for v in counts if v is not None]
            for name, counts in values.items()
        }
        return {
            "total_tokens_consumed": sum(known["total_tokens"])
            if known["total_tokens"]
            else None,
            "total_thinking_tokens": sum(known["thinking_tokens"])
            if known["thinking_tokens"]
            else None,
            **{
                f"avg_{name}": _ratio(sum(known[name]), len(known[name]))
                for name in ("prompt_tokens", "completion_tokens", "thinking_tokens")
            },
            "usage_known_cases": {k: len(v) for k, v in known.items()},
            "usage_coverage": {
                k: _ratio(len(v), len(self.reports)) for k, v in known.items()
            },
            # Failed attempts have unobserved costs even when a retry succeeds.
            "token_accounting_complete": bool(self.reports)
            and all(
                r.metadata.total_tokens is not None and r.metadata.request_attempts == 1
                for r in self.reports
            ),
        }


class ExecutionTimeMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        known = [
            r.metadata.case_latency_seconds
            for r in self.reports
            if r.metadata.case_latency_seconds is not None
        ]
        llm = [
            r.metadata.llm_latency_seconds
            for r in self.reports
            if r.metadata.llm_latency_seconds is not None
        ]
        return {
            "total_execution_seconds": sum(known) if known else None,
            "avg_latency_seconds": _ratio(sum(known), len(known)),
            "latency_known_cases": len(known),
            "latency_coverage": _ratio(len(known), len(self.reports)),
            "total_llm_seconds": sum(llm) if llm else None,
            "avg_llm_latency_seconds": _ratio(sum(llm), len(llm)),
            "llm_latency_known_cases": len(llm),
            "llm_latency_coverage": _ratio(len(llm), len(self.reports)),
        }


class RefusalRateMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        count = sum(r.refusal is True for r in self.reports)
        return {
            "refusal_count": count,
            "refusal_rate": _ratio(count, len(self.reports)),
        }


class InfrastructureErrorRateMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        count = sum(
            r.error_category is EvaluationErrorCategory.API for r in self.reports
        )
        return {
            "infra_error_count": count,
            "infrastructure_error_rate": _ratio(count, len(self.reports)),
        }


class ResponseErrorRateMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        count = sum(
            r.error_category is EvaluationErrorCategory.RESPONSE for r in self.reports
        )
        return {
            "response_error_count": count,
            "response_error_rate": _ratio(count, len(self.reports)),
        }


class CodeExecutionErrorRateMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        count = sum(
            r.error_category is EvaluationErrorCategory.EXECUTION for r in self.reports
        )
        return {
            "execution_error_count": count,
            "execution_error_rate": _ratio(count, len(self.reports)),
        }


class ValidResponseAccuracyMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        valid = [r for r in self.reports if r.valid_response]
        return {
            "valid_response_accuracy": _ratio(
                sum(r.is_sat_correct for r in valid), len(valid)
            ),
            "valid_responses_evaluated": len(valid),
            "coverage": _ratio(len(valid), len(self.reports)),
        }
