"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from collections import Counter
from collections.abc import Sequence

from pydantic import JsonValue

from logicmus_eval.enums import EvaluationErrorType
from logicmus_eval.models.evaluation import (
    EvaluationCaseReport,
)


def _ratio(numerator: float, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def accounting_counts(
    reports: Sequence[EvaluationCaseReport], planned: int
) -> dict[str, JsonValue]:
    """Each primary error counts a case once, independent of diagnostic tags."""
    errors: Counter[EvaluationErrorType] = Counter(
        r.error_type for r in reports if r.error_type is not None
    )
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
