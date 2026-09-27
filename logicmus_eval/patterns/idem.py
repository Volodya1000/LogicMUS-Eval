# pylint: disable=duplicate-code
import random

from logicmus_eval.enums import OperatorType, RulePrefix, TemplatePackId
from logicmus_eval.models.rules import BaseRule, FactRule, ImpliesRule
from logicmus_eval.patterns.base import BasePatternStrategy, PatternGenerationResult
from logicmus_eval.templates import TEMPLATES, negate


class IdemPatternStrategy(BasePatternStrategy):
    name = "idem"

    @classmethod
    def supports(cls, mus_size: int) -> bool:
        # Two conflicting implications over one antecedent → exactly 2 vars.
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

        fact_template = rng.choice(pack_templates[OperatorType.FACT])
        core_rules.append(
            FactRule(
                id=f"{RulePrefix.CORE_RULE}1",
                text=fact_template.replace("{var}", pred_a),
                variable=var_a,
                predicate=pred_a,
                polarity=True,
            )
        )

        implies_template = rng.choice(pack_templates[OperatorType.IMPLIES])
        core_rules.append(
            ImpliesRule(
                id=f"{RulePrefix.CORE_RULE}2",
                text=implies_template.replace("{ant}", pred_a).replace(
                    "{cons}", pred_b
                ),
                antecedent=var_a,
                consequent=var_b,
                antecedent_predicate=pred_a,
                consequent_predicate=pred_b,
                antecedent_polarity=True,
                consequent_polarity=True,
            )
        )

        conflict_polarity = bool(is_satisfiable)
        conflict_text = pred_b if conflict_polarity else negate(pred_b)
        core_rules.append(
            ImpliesRule(
                id=f"{RulePrefix.CORE_RULE}3",
                text=implies_template.replace("{ant}", pred_a).replace(
                    "{cons}", conflict_text
                ),
                antecedent=var_a,
                consequent=var_b,
                antecedent_predicate=pred_a,
                consequent_predicate=pred_b,
                antecedent_polarity=True,
                consequent_polarity=conflict_polarity,
            )
        )

        expected_mus = [r.id for r in core_rules] if not is_satisfiable else []
        return PatternGenerationResult(
            core_rules=core_rules, expected_mus_ids=expected_mus
        )
