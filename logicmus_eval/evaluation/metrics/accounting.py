"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from collections import Counter
from collections.abc import Sequence

from pydantic import JsonValue

from logicmus_eval.enums import EvaluationErrorType
from logicmus_eval.evaluation.metrics.semantics import contributions
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
        "valid_responses_evaluated": int(sum(contributions(reports, "coverage"))),
        "unsat_evaluated": len(contributions(reports, "mus_exact_match")),
        "correct_sat": int(sum(contributions(reports, "sat_accuracy"))),
        "refusal_count": sum(r.refusal is True for r in reports),
        "error_count": sum(errors.values()),
        "error_counts": dict(sorted(errors.items())),
    }
