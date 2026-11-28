"""Offline fixed duplicate cues; passing these is not proof of no leakage.

Each baseline predicts SAT iff at least two rules have the same feature key.
Features use rules alone. Gold labels are used only to score those predictions.
Canonicalization is signed structural equality with commutative argument/order
normalization, not a decision procedure for arbitrary logical equivalence.
"""

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from logicmus_eval.enums import OperatorType
from logicmus_eval.experiment_plan import canonical_json
from logicmus_eval.models.rules import (
    AndImpliesRule,
    BaseRule,
    FactRule,
    ImpliesRule,
    NoiseRule,
    NumericEQRule,
    NumericGTRule,
    NumericLTRule,
    NumericRule,
    OrFactRule,
    TerminalRule,
)
from logicmus_eval.models.test_case import LogicTestCase

RuleInput = BaseRule | Mapping[str, object]
RULE_MODELS: dict[str, type[BaseRule]] = {
    OperatorType.FACT.value: FactRule,
    OperatorType.TERMINAL.value: TerminalRule,
    OperatorType.NOISE.value: NoiseRule,
    OperatorType.IMPLIES.value: ImpliesRule,
    OperatorType.AND_IMPLIES.value: AndImpliesRule,
    OperatorType.OR_FACT.value: OrFactRule,
    OperatorType.NUMERIC.value: NumericRule,
    OperatorType.NUMERIC_GT.value: NumericGTRule,
    OperatorType.NUMERIC_LT.value: NumericLTRule,
    OperatorType.NUMERIC_EQ.value: NumericEQRule,
}


def _normalize_rule(rule: RuleInput) -> BaseRule:
    """Restore concrete rule types from the JSONL list[Any] storage contract."""
    if isinstance(rule, BaseRule):
        return rule
    kind = rule.get("operator_type")
    if not isinstance(kind, str) or kind not in RULE_MODELS:
        raise ValueError(f"Unsupported rule type for duplicate audit: {kind!r}")
    payload = dict(rule)
    payload["operator_type"] = OperatorType(kind)
    return RULE_MODELS[kind].model_validate(payload, strict=True)


class DuplicateFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    duplicate_text: bool
    duplicate_formula: bool


class DuplicateBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    prediction_rule: Literal["duplicate -> SAT; otherwise UNSAT"] = (
        "duplicate -> SAT; otherwise UNSAT"
    )
    confusion_axes: Literal["rows=gold; columns=prediction"] = (
        "rows=gold; columns=prediction"
    )
    confusion_matrix: dict[str, dict[str, int]]
    cases: int
    independent_families: int
    accuracy: float
    balanced_accuracy: float


def canonical_formula(rule: RuleInput) -> str:
    """Ignore ID, text, predicate wording and service role; retain signed atoms."""
    rule = _normalize_rule(rule)
    if isinstance(rule, (FactRule, TerminalRule, NoiseRule)):
        return canonical_json(("literal", rule.variable, rule.polarity))
    if isinstance(rule, ImpliesRule):
        return canonical_json(
            (
                "implies",
                (rule.antecedent, rule.antecedent_polarity),
                (rule.consequent, rule.consequent_polarity),
            )
        )
    if isinstance(rule, AndImpliesRule):
        return canonical_json(
            (
                "and_implies",
                sorted(
                    [
                        (rule.antecedent1, rule.antecedent1_polarity),
                        (rule.antecedent2, rule.antecedent2_polarity),
                    ]
                ),
                (rule.consequent, rule.consequent_polarity),
            )
        )
    if isinstance(rule, OrFactRule):
        return canonical_json(
            (
                "or",
                sorted(
                    [
                        (rule.variable1, rule.polarity1),
                        (rule.variable2, rule.polarity2),
                    ]
                ),
            )
        )
    if isinstance(rule, NumericRule):
        left, right, operator = rule.left_var, rule.right_var, rule.operator
        if operator == ">":
            left, right, operator = right, left, "<"
        elif operator == "==":
            left, right = sorted((left, right))
        return canonical_json(("numeric", operator, left, right))
    raise ValueError(
        f"Unsupported rule type for duplicate audit: {type(rule).__name__}"
    )


def duplicate_features(rules: Sequence[RuleInput]) -> DuplicateFeatures:
    normalized = [_normalize_rule(rule) for rule in rules]
    return DuplicateFeatures(
        duplicate_text=len({rule.text for rule in normalized}) != len(rules),
        duplicate_formula=len({canonical_formula(rule) for rule in normalized})
        != len(rules),
    )


def audit_duplicates(cases: Sequence[LogicTestCase]) -> dict[str, DuplicateBaseline]:
    """Score two preregistered rules without fitting or selecting a direction."""
    if not cases or {case.is_satisfiable for case in cases} != {False, True}:
        raise ValueError("Duplicate audit requires both SAT and UNSAT examples")
    if len({case.metadata.get("protocol_version") for case in cases}) != 1:
        raise ValueError("Duplicate audit must not pool different protocol versions")
    features = [duplicate_features(case.rules) for case in cases]
    result = {}
    families = {str(case.metadata.get("family_id", case.case_id)) for case in cases}
    for name, predictions in (
        ("exact_text", [value.duplicate_text for value in features]),
        ("canonical_formula", [value.duplicate_formula for value in features]),
    ):
        matrix = {
            gold: {prediction: 0 for prediction in ("SAT", "UNSAT")}
            for gold in ("SAT", "UNSAT")
        }
        for case, prediction in zip(cases, predictions):
            matrix["SAT" if case.is_satisfiable else "UNSAT"][
                "SAT" if prediction else "UNSAT"
            ] += 1
        result[name] = DuplicateBaseline(
            confusion_matrix=matrix,
            cases=len(cases),
            independent_families=len(families),
            accuracy=sum(matrix[label][label] for label in matrix) / len(cases),
            balanced_accuracy=sum(
                matrix[label][label] / sum(matrix[label].values()) for label in matrix
            )
            / 2,
        )
    return result
