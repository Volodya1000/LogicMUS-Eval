# pylint: disable=duplicate-code
import random

from src.enums import OperatorType, RulePrefix, TemplatePackId
from src.models.rules import BaseRule, FactRule, ImpliesRule, TerminalRule
from src.patterns.base import BasePatternStrategy, PatternGenerationResult
from src.templates import TEMPLATES


class DirectPatternStrategy(BasePatternStrategy):
    name = "direct"

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

        fact_template = rng.choice(pack_templates[OperatorType.FACT])
        fact_pred = predicate_mapping[core_variables[0]]

        core_rules.append(
            FactRule(
                id=f"{RulePrefix.CORE_RULE}1",
                text=fact_template.replace("{var}", fact_pred),
                variable=core_variables[0],
                predicate=fact_pred,
                polarity=True,
            )
        )

        for i in range(len(core_variables) - 1):
            v_curr = core_variables[i]
            v_next = core_variables[i + 1]
            implies_template = rng.choice(pack_templates[OperatorType.IMPLIES])
            ant_pred = predicate_mapping[v_curr]
            cons_pred = predicate_mapping[v_next]
            implies_text = implies_template.replace("{ant}", ant_pred).replace(
                "{cons}", cons_pred
            )

            core_rules.append(
                ImpliesRule(
                    id=f"{RulePrefix.CORE_RULE}{i + 2}",
                    text=implies_text,
                    antecedent=v_curr,
                    consequent=v_next,
                    antecedent_predicate=ant_pred,
                    consequent_predicate=cons_pred,
                    antecedent_polarity=True,
                    consequent_polarity=True,
                )
            )

        last_var = core_variables[-1]
        term_polarity = bool(is_satisfiable)
        term_template = rng.choice(pack_templates[OperatorType.TERMINAL])
        term_pred = predicate_mapping[last_var]
        prefix_not = "" if term_polarity else "not "

        core_rules.append(
            TerminalRule(
                id=f"{RulePrefix.CORE_RULE}{len(core_rules) + 1}",
                text=term_template.replace("{var}", f"{prefix_not}{term_pred}"),
                variable=last_var,
                predicate=term_pred,
                polarity=term_polarity,
            )
        )

        expected_mus = [r.id for r in core_rules] if not is_satisfiable else []
        return PatternGenerationResult(
            core_rules=core_rules, expected_mus_ids=expected_mus
        )
