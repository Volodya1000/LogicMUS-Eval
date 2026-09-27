# pylint: disable=duplicate-code
import random

from logicmus_eval.enums import OperatorType, RulePrefix, TemplatePackId
from logicmus_eval.models.rules import AndImpliesRule, BaseRule, FactRule, TerminalRule
from logicmus_eval.patterns.base import BasePatternStrategy, PatternGenerationResult
from logicmus_eval.templates import TEMPLATES, negate


class MergePatternStrategy(BasePatternStrategy):
    name = "merge"

    @classmethod
    def supports(cls, mus_size: int) -> bool:
        # AND-implies with two antecedents + one consequent → exactly 3 vars.
        return mus_size == 3

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
        ant1_var, ant2_var = core_variables[0], core_variables[1]
        cons_var = core_variables[2]
        ant1_p, ant2_p = predicate_mapping[ant1_var], predicate_mapping[ant2_var]
        cons_p = predicate_mapping[cons_var]

        core_rules.append(
            FactRule(
                id=f"{RulePrefix.CORE_RULE}1",
                text=pack_templates[OperatorType.FACT][0].replace("{var}", ant1_p),
                variable=ant1_var,
                predicate=ant1_p,
                polarity=True,
            )
        )

        core_rules.append(
            FactRule(
                id=f"{RulePrefix.CORE_RULE}2",
                text=pack_templates[OperatorType.FACT][0].replace("{var}", ant2_p),
                variable=ant2_var,
                predicate=ant2_p,
                polarity=True,
            )
        )

        and_text = (
            pack_templates[OperatorType.AND_IMPLIES][0]
            .replace("{ant1}", ant1_p)
            .replace("{ant2}", ant2_p)
            .replace("{cons}", cons_p)
        )
        core_rules.append(
            AndImpliesRule(
                id=f"{RulePrefix.CORE_RULE}3",
                text=and_text,
                antecedent1=ant1_var,
                antecedent2=ant2_var,
                consequent=cons_var,
                antecedent1_predicate=ant1_p,
                antecedent2_predicate=ant2_p,
                consequent_predicate=cons_p,
            )
        )

        term_polarity = bool(is_satisfiable)
        term_text = cons_p if term_polarity else negate(cons_p)

        core_rules.append(
            TerminalRule(
                id=f"{RulePrefix.CORE_RULE}4",
                text=pack_templates[OperatorType.TERMINAL][0].replace(
                    "{var}", term_text
                ),
                variable=cons_var,
                predicate=cons_p,
                polarity=term_polarity,
            )
        )

        expected_mus = [r.id for r in core_rules] if not is_satisfiable else []
        return PatternGenerationResult(
            core_rules=core_rules, expected_mus_ids=expected_mus
        )
