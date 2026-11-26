"""Label-independent, pair-preserving presentation of symbolic constraints."""

import random

from logicmus_eval.enums import OperatorType, TemplatePackId
from logicmus_eval.models.rules import (
    AndImpliesRule,
    BaseRule,
    FactRule,
    ImpliesRule,
    NoiseRule,
    NumericGTRule,
    NumericLTRule,
    NumericRule,
    OrFactRule,
    TerminalRule,
)
from logicmus_eval.templates import TEMPLATES, negate


def _literal(predicate: str, polarity: bool) -> str:
    return predicate if polarity else f"({negate(predicate)})"


def render_rule(rule: BaseRule, pack_id: TemplatePackId, rng: random.Random) -> str:
    """Render exactly the polarities/operators consumed by the Z3 oracle."""
    templates = TEMPLATES[pack_id]
    if isinstance(rule, (FactRule, TerminalRule, NoiseRule)):
        pool = templates[rule.operator_type]
        if isinstance(rule, NoiseRule):
            pool = [
                t
                for op in (OperatorType.FACT, OperatorType.TERMINAL, OperatorType.NOISE)
                for t in templates[op]
            ]
        return rng.choice(pool).format(var=_literal(rule.predicate, rule.polarity))
    if isinstance(rule, ImpliesRule):
        return rng.choice(templates[rule.operator_type]).format(
            ant=_literal(rule.antecedent_predicate, rule.antecedent_polarity),
            cons=_literal(rule.consequent_predicate, rule.consequent_polarity),
        )
    if isinstance(rule, AndImpliesRule):
        return rng.choice(templates[rule.operator_type]).format(
            ant1=_literal(rule.antecedent1_predicate, rule.antecedent1_polarity),
            ant2=_literal(rule.antecedent2_predicate, rule.antecedent2_polarity),
            cons=_literal(rule.consequent_predicate, rule.consequent_polarity),
        )
    if isinstance(rule, OrFactRule):
        return rng.choice(templates[rule.operator_type]).format(
            var1=_literal(rule.predicate1, rule.polarity1),
            var2=_literal(rule.predicate2, rule.polarity2),
        )
    if isinstance(rule, NumericRule):
        return rng.choice(templates[rule.operator_type]).format(
            left=rule.left_predicate, right=rule.right_predicate
        )
    raise ValueError(f"No text renderer for {type(rule).__name__}")


def present_rules(
    rules: list[BaseRule], mapping: dict[str, str], pack_id: TemplatePackId, seed: int
) -> list[BaseRule]:
    """Complement Boolean atoms and reverse numeric notation, never using labels.

    Boolean substitution x -> not(x) is bijective on assignments. Rewriting
    a > b as b < a preserves the constraint. Both members of a pair use the
    same substitutions, orientation draws and text-template draws.
    """
    rng = random.Random(f"presentation:{seed}")
    complements = {var: rng.choice((False, True)) for var in mapping}
    out: list[BaseRule] = []
    for original in rules:
        rule = original.model_copy(deep=True)
        if isinstance(rule, (FactRule, TerminalRule, NoiseRule)):
            rule.polarity ^= complements[rule.variable]
        elif isinstance(rule, ImpliesRule):
            rule.antecedent_polarity ^= complements[rule.antecedent]
            rule.consequent_polarity ^= complements[rule.consequent]
        elif isinstance(rule, AndImpliesRule):
            rule.antecedent1_polarity ^= complements[rule.antecedent1]
            rule.antecedent2_polarity ^= complements[rule.antecedent2]
            rule.consequent_polarity ^= complements[rule.consequent]
        elif isinstance(rule, OrFactRule):
            rule.polarity1 ^= complements[rule.variable1]
            rule.polarity2 ^= complements[rule.variable2]
        elif (
            isinstance(rule, NumericRule)
            and rng.choice((False, True))
            and rule.operator in (">", "<")
        ):
            cls = NumericLTRule if rule.operator == ">" else NumericGTRule
            rule = cls(
                id=rule.id,
                text="",
                left_var=rule.right_var,
                right_var=rule.left_var,
                left_predicate=rule.right_predicate,
                right_predicate=rule.left_predicate,
            )
        rule.text = render_rule(rule, pack_id, rng)
        out.append(rule)
    return out
