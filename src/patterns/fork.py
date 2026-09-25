import random

from src.enums import OperatorType, RulePrefix, TemplatePackId
from src.models.rules import FactRule, ImpliesRule, TerminalRule
from src.patterns.base import BasePatternStrategy, PatternGenerationResult
from src.templates import TEMPLATES


class ForkPatternStrategy(BasePatternStrategy):
    def generate_pattern(
            self,
            mus_size: int,
            is_satisfiable: bool,
            core_variables: list[str],
            predicate_mapping: dict[str, str],
            pack_id: TemplatePackId,
            rng: random.Random
    ) -> PatternGenerationResult:
        pack_templates = TEMPLATES[pack_id]
        core_rules = []

        root_var = core_variables[0]
        root_pred = predicate_mapping[root_var]

        fact_template = rng.choice(pack_templates[OperatorType.FACT])
        core_rules.append(FactRule(
            id=f"{RulePrefix.CORE_RULE}1",
            text=fact_template.replace("{var}", root_pred),
            variable=root_var,
            predicate=root_pred,
            polarity=True
        ))

        for i in range(1, len(core_variables)):
            branch_var = core_variables[i]
            branch_pred = predicate_mapping[branch_var]
            implies_template = rng.choice(pack_templates[OperatorType.IMPLIES])

            core_rules.append(ImpliesRule(
                id=f"{RulePrefix.CORE_RULE}{i + 1}",
                text=implies_template.replace("{ant}", root_pred).replace("{cons}", branch_pred),
                antecedent=root_var,
                consequent=branch_var,
                antecedent_predicate=root_pred,
                consequent_predicate=branch_pred,
                antecedent_polarity=True,
                consequent_polarity=True
            ))

        term_var = core_variables[-1]
        term_pred = predicate_mapping[term_var]
        term_polarity = bool(is_satisfiable)
        term_template = rng.choice(pack_templates[OperatorType.TERMINAL])
        prefix_not = "" if term_polarity else "not "

        core_rules.append(TerminalRule(
            id=f"{RulePrefix.CORE_RULE}{len(core_variables) + 1}",
            text=term_template.replace("{var}", f"{prefix_not}{term_pred}"),
            variable=term_var,
            predicate=term_pred,
            polarity=term_polarity
        ))

        expected_mus = [r.id for r in core_rules] if not is_satisfiable else []
        return PatternGenerationResult(core_rules=core_rules, expected_mus_ids=expected_mus)
