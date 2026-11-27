"""Controlled-only presentation without literal wording that marks noise roles."""

import random

from logicmus_eval.enums import TemplatePackId
from logicmus_eval.experiment_plan import content_id
from logicmus_eval.generation_rendering import present_rules as present_legacy_rules
from logicmus_eval.generation_rendering import render_rule
from logicmus_eval.models.rules import BaseRule, FactRule, NoiseRule, TerminalRule


def present_rules(
    rules: list[BaseRule], mapping: dict[str, str], pack_id: TemplatePackId, seed: int
) -> list[BaseRule]:
    rendered = present_legacy_rules(rules, mapping, pack_id, seed)
    for rule in rendered:
        if isinstance(rule, (FactRule, TerminalRule, NoiseRule)):
            # The NOISE renderer draws from the union of all literal templates.
            # Apply that same pool to every literal, retaining the real rule type.
            literal = NoiseRule(
                id=rule.id,
                text="",
                variable=rule.variable,
                predicate=rule.predicate,
                polarity=rule.polarity,
            )
            rule.text = render_rule(
                literal,
                pack_id,
                random.Random(content_id("literal_text", seed, rule.id)),
            )
    return rendered
