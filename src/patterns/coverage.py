# pylint: disable=duplicate-code
import random

from src.enums import OperatorType, RulePrefix, TemplatePackId
from src.models.rules import BaseRule, FactRule, OrFactRule
from src.patterns.base import BasePatternStrategy, PatternGenerationResult
from src.templates import TEMPLATES


class CoveragePatternStrategy(BasePatternStrategy):
    name = "coverage"

    @classmethod
    def supports(cls, mus_size: int) -> bool:
        # OR-fact pattern requires exactly 2 core variables.
        return mus_size == 2

    # pylint: disable=too-many-arguments, too-many-positional-arguments, too-many-locals
    def generate_pattern(
        self,
        mus_size: int,
        is_satisfiable: bool,
        core_variables: list[str],
        predicate_mapping: dict[str, str],
        pack_id: TemplatePackId,
        rng: random.Random,
    ) -> PatternGenerationResult:
        pack_templates = TEMPLATES[pack_id]
        core_rules: list[BaseRule] = []

        var_a = core_variables[0]
        var_b = core_variables[1]
        pred_a = predicate_mapping[var_a]
        pred_b = predicate_mapping[var_b]

        or_template = rng.choice(pack_templates[OperatorType.OR_FACT])
        core_rules.append(
            OrFactRule(
                id=f"{RulePrefix.CORE_RULE}1",
                text=or_template.replace("{var1}", pred_a).replace("{var2}", pred_b),
                variable1=var_a,
                variable2=var_b,
                predicate1=pred_a,
                predicate2=pred_b,
            )
        )

        fact_template = rng.choice(pack_templates[OperatorType.FACT])
        core_rules.append(
            FactRule(
                id=f"{RulePrefix.CORE_RULE}2",
                text=fact_template.replace("{var}", f"not {pred_a}"),
                variable=var_a,
                predicate=pred_a,
                polarity=False,
            )
        )

        polarity_b = bool(is_satisfiable)
        text_b = pred_b if polarity_b else f"not {pred_b}"
        core_rules.append(
            FactRule(
                id=f"{RulePrefix.CORE_RULE}3",
                text=fact_template.replace("{var}", text_b),
                variable=var_b,
                predicate=pred_b,
                polarity=polarity_b,
            )
        )

        expected_mus = [r.id for r in core_rules] if not is_satisfiable else []
        return PatternGenerationResult(
            core_rules=core_rules, expected_mus_ids=expected_mus
        )
