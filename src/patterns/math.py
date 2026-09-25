import random

from src.enums import OperatorType, RulePrefix, TemplatePackId
from src.models.rules import BaseRule, NumericEQRule, NumericGTRule, NumericLTRule
from src.patterns.base import BasePatternStrategy, PatternGenerationResult
from src.templates import TEMPLATES


class MathPatternStrategy(BasePatternStrategy):
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
        pack_templates = TEMPLATES.get(pack_id, TEMPLATES[TemplatePackId.MATH_PACK])
        if OperatorType.NUMERIC_GT not in pack_templates:
            pack_templates = TEMPLATES[TemplatePackId.MATH_PACK]

        gt_templates = pack_templates[OperatorType.NUMERIC_GT]
        lt_templates = pack_templates[OperatorType.NUMERIC_LT]
        eq_templates = pack_templates[OperatorType.NUMERIC_EQ]

        core_rules: list[BaseRule] = []

        if mus_size <= 1:
            var_name = core_variables[0]
            pred_name = predicate_mapping[var_name]
            if is_satisfiable:
                tmpl = rng.choice(eq_templates)
                text = tmpl.replace("{left}", pred_name).replace("{right}", pred_name)
                core_rules.append(
                    NumericEQRule(
                        id=f"{RulePrefix.CORE_RULE}1",
                        text=text,
                        left_var=var_name,
                        right_var=var_name,
                        left_predicate=pred_name,
                        right_predicate=pred_name,
                    )
                )
            else:
                tmpl = rng.choice(gt_templates)
                text = tmpl.replace("{left}", pred_name).replace("{right}", pred_name)
                core_rules.append(
                    NumericGTRule(
                        id=f"{RulePrefix.CORE_RULE}1",
                        text=text,
                        left_var=var_name,
                        right_var=var_name,
                        left_predicate=pred_name,
                        right_predicate=pred_name,
                    )
                )
            expected_mus = [r.id for r in core_rules] if not is_satisfiable else []
            return PatternGenerationResult(
                core_rules=core_rules, expected_mus_ids=expected_mus
            )

        for i in range(mus_size - 1):
            left_v = core_variables[i]
            right_v = core_variables[i + 1]
            left_p = predicate_mapping[left_v]
            right_p = predicate_mapping[right_v]

            tmpl = rng.choice(gt_templates)
            rule_text = tmpl.replace("{left}", left_p).replace("{right}", right_p)
            core_rules.append(
                NumericGTRule(
                    id=f"{RulePrefix.CORE_RULE}{i + 1}",
                    text=rule_text,
                    left_var=left_v,
                    right_var=right_v,
                    left_predicate=left_p,
                    right_predicate=right_p,
                )
            )

        last_v = core_variables[mus_size - 1]
        first_v = core_variables[0]
        last_p = predicate_mapping[last_v]
        first_p = predicate_mapping[first_v]

        if not is_satisfiable:
            tmpl = rng.choice(gt_templates)
            rule_text = tmpl.replace("{left}", last_p).replace("{right}", first_p)
            core_rules.append(
                NumericGTRule(
                    id=f"{RulePrefix.CORE_RULE}{mus_size}",
                    text=rule_text,
                    left_var=last_v,
                    right_var=first_v,
                    left_predicate=last_p,
                    right_predicate=first_p,
                )
            )
        else:
            tmpl = rng.choice(lt_templates)
            rule_text = tmpl.replace("{left}", last_p).replace("{right}", first_p)
            core_rules.append(
                NumericLTRule(
                    id=f"{RulePrefix.CORE_RULE}{mus_size}",
                    text=rule_text,
                    left_var=last_v,
                    right_var=first_v,
                    left_predicate=last_p,
                    right_predicate=first_p,
                )
            )

        expected_mus = [r.id for r in core_rules] if not is_satisfiable else []
        return PatternGenerationResult(
            core_rules=core_rules, expected_mus_ids=expected_mus
        )
