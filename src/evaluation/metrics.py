from abc import ABC, abstractmethod
from typing import Any

from src.models.evaluation import CasePrediction, ExtractionMetadata
from src.models.test_case import LogicTestCase


class BaseMetric(ABC):
    @abstractmethod
    def update(
        self,
        case: LogicTestCase,
        prediction: CasePrediction,
        metadata: ExtractionMetadata,
    ) -> None:
        pass

    @abstractmethod
    def compute(self) -> dict[str, Any]:
        pass

    @abstractmethod
    def reset(self) -> None:
        pass


class SatAccuracyMetric(BaseMetric):
    def __init__(self) -> None:
        self.total_count = 0
        self.correct_count = 0

    def update(
        self,
        case: LogicTestCase,
        prediction: CasePrediction,
        metadata: ExtractionMetadata,
    ) -> None:
        if prediction.is_sat is not None:
            self.total_count += 1
            if prediction.is_sat == case.is_satisfiable:
                self.correct_count += 1

    def compute(self) -> dict[str, Any]:
        acc = self.correct_count / self.total_count if self.total_count > 0 else 0.0
        return {
            "sat_accuracy": round(acc, 4),
            "total_evaluated": self.total_count,
            "correct_sat": self.correct_count,
        }

    def reset(self) -> None:
        self.total_count = 0
        self.correct_count = 0


class MusValidMetric(BaseMetric):
    def __init__(self) -> None:
        self.unsat_total = 0
        self.exact_matches = 0
        self.total_precision = 0.0
        self.total_recall = 0.0

    def update(
        self,
        case: LogicTestCase,
        prediction: CasePrediction,
        metadata: ExtractionMetadata,
    ) -> None:
        if not case.is_satisfiable:
            self.unsat_total += 1
            expected = set(case.mus_expected)
            predicted = set(prediction.conflict_core)

            if expected == predicted:
                self.exact_matches += 1

            intersection = len(expected.intersection(predicted))
            prec = intersection / len(predicted) if predicted else 0.0
            rec = intersection / len(expected) if expected else 0.0

            self.total_precision += prec
            self.total_recall += rec

    def compute(self) -> dict[str, Any]:
        if self.unsat_total == 0:
            return {
                "mus_exact_match": 0.0,
                "mus_precision": 0.0,
                "mus_recall": 0.0,
                "mus_f1": 0.0,
            }

        mean_prec = self.total_precision / self.unsat_total
        mean_rec = self.total_recall / self.unsat_total
        f1 = (
            (2 * mean_prec * mean_rec / (mean_prec + mean_rec))
            if (mean_prec + mean_rec) > 0
            else 0.0
        )

        return {
            "mus_exact_match": round(self.exact_matches / self.unsat_total, 4),
            "mus_precision": round(mean_prec, 4),
            "mus_recall": round(mean_rec, 4),
            "mus_f1": round(f1, 4),
            "unsat_evaluated": self.unsat_total,
        }

    def reset(self) -> None:
        self.unsat_total = 0
        self.exact_matches = 0
        self.total_precision = 0.0
        self.total_recall = 0.0


class TokenUsageMetric(BaseMetric):
    def __init__(self) -> None:
        self.cases_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_thinking_tokens = 0
        self.total_tokens = 0

    def update(
        self,
        case: LogicTestCase,
        prediction: CasePrediction,
        metadata: ExtractionMetadata,
    ) -> None:
        self.cases_count += 1
        self.total_prompt_tokens += metadata.prompt_tokens
        self.total_completion_tokens += metadata.completion_tokens
        self.total_thinking_tokens += metadata.thinking_tokens
        self.total_tokens += metadata.total_tokens

    def compute(self) -> dict[str, Any]:
        avg_prompt = (
            self.total_prompt_tokens / self.cases_count if self.cases_count > 0 else 0.0
        )
        avg_completion = (
            self.total_completion_tokens / self.cases_count
            if self.cases_count > 0
            else 0.0
        )
        avg_thinking = (
            self.total_thinking_tokens / self.cases_count
            if self.cases_count > 0
            else 0.0
        )

        return {
            "total_tokens_consumed": self.total_tokens,
            "total_thinking_tokens": self.total_thinking_tokens,
            "avg_prompt_tokens": round(avg_prompt, 2),
            "avg_completion_tokens": round(avg_completion, 2),
            "avg_thinking_tokens": round(avg_thinking, 2),
        }

    def reset(self) -> None:
        self.cases_count = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.total_thinking_tokens = 0
        self.total_tokens = 0


class ExecutionTimeMetric(BaseMetric):
    def __init__(self) -> None:
        self.cases_count = 0
        self.total_duration_sec = 0.0

    def update(
        self,
        case: LogicTestCase,
        prediction: CasePrediction,
        metadata: ExtractionMetadata,
    ) -> None:
        self.cases_count += 1
        self.total_duration_sec += metadata.latency_seconds

    def compute(self) -> dict[str, Any]:
        avg_time = (
            self.total_duration_sec / self.cases_count if self.cases_count > 0 else 0.0
        )
        return {
            "total_execution_seconds": round(self.total_duration_sec, 2),
            "avg_latency_seconds": round(avg_time, 2),
        }

    def reset(self) -> None:
        self.cases_count = 0
        self.total_duration_sec = 0.0
