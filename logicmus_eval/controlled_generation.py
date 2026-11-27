"""N-independent construction, nested distractors and stable insertion ordering."""

import random

from logicmus_eval.controlled_rendering import present_rules
from logicmus_eval.experiment_plan import (
    PATTERNS,
    PROTOCOL_VERSION,
    ExperimentCell,
    ExperimentPlan,
    case_identity,
    content_id,
    family_identity,
)
from logicmus_eval.models.rules import BaseRule, NoiseRule
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.templates import PREDICATE_POOL, get_template_pack_id


def generate_cell(plan: ExperimentPlan, cell: ExperimentCell) -> list[LogicTestCase]:
    """Generate exactly the registered cell; never round-robin or substitute."""
    validated = ExperimentPlan.model_validate(plan.model_dump())
    if cell not in validated.cells():
        raise ValueError("Cell is not in the validated plan")
    return [
        case
        for seed in sorted(plan.seeds)
        for index in range(plan.pairs_per_seed)
        for case in _generate_pair(plan, cell, seed, index)
    ]


# pylint: disable=too-many-locals
def _generate_pair(
    plan: ExperimentPlan, cell: ExperimentCell, seed: int, index: int
) -> tuple[LogicTestCase, LogicTestCase]:
    strategy = PATTERNS[cell.pattern_id]()
    family_id = family_identity(cell.pattern_id, cell.k, seed, index)
    pair_id = content_id(family_id, cell.n)
    construction_count = strategy.core_rule_count(cell.k)
    core_var_count = strategy.core_variable_count(cell.k)
    noise_count = cell.n - construction_count
    # Permute the entire fixed pool, never a prefix whose size depends on N.
    aliases = [f"p{i + 1}" for i in range(len(PREDICATE_POOL))]
    random.Random(content_id(family_id, "aliases")).shuffle(aliases)
    predicates = list(PREDICATE_POOL)
    random.Random(content_id(family_id, "predicates")).shuffle(predicates)
    mapping = dict(zip(aliases, predicates))
    used_variables = aliases[: core_var_count + noise_count]
    visible_mapping = {var: mapping[var] for var in sorted(used_variables)}
    pack = strategy.forced_pack_id or get_template_pack_id(
        int(content_id(family_id, "pack"), 16)
    )
    noise: list[BaseRule] = []
    for i in range(noise_count):
        var = aliases[core_var_count + i]
        noise_rule = NoiseRule(
            id=f"noise:{i + 1}",
            text="",
            variable=var,
            predicate=mapping[var],
            polarity=random.Random(content_id(family_id, "noise", i)).choice(
                (True, False)
            ),
        )
        noise.extend(
            present_rules(
                [noise_rule],
                mapping,
                pack,
                int(content_id(family_id, "noise_presentation", i), 16),
            )
        )

    cases = []
    for is_sat in (True, False):
        result = strategy.generate_pattern(
            mus_size=cell.k,
            is_satisfiable=is_sat,
            core_variables=aliases[:core_var_count],
            predicate_mapping=mapping,
            pack_id=pack,
            rng=random.Random(content_id(family_id, "construction")),
        )
        if len(result.core_rules) != construction_count:
            raise RuntimeError("Unexpected construction size")
        core_ids = {
            r.id: f"construction:{i + 1}" for i, r in enumerate(result.core_rules)
        }
        expected = [core_ids[rid] for rid in result.expected_mus_ids]
        construction = present_rules(
            result.core_rules,
            mapping,
            pack,
            int(content_id(family_id, "presentation"), 16),
        )
        for rule in construction:
            rule.id = core_ids[rule.id]
        all_rules = construction + [r.model_copy(deep=True) for r in noise]
        all_rules.sort(key=lambda r: (content_id(family_id, "order", r.id), r.id))
        correspondence = {f"R{i + 1}": r.id for i, r in enumerate(all_rules)}
        display_ids = {uid: rid for rid, uid in correspondence.items()}
        for rule in all_rules:
            rule.id = display_ids[rule.id]
        case_uid = case_identity(cell, seed, index, is_sat)
        cases.append(
            LogicTestCase(
                case_id=case_uid,
                mus_size=cell.k,
                is_satisfiable=is_sat,
                template_pack_id=pack,
                predicate_mapping=visible_mapping,
                rules=all_rules,
                mus_expected=[display_ids[uid] for uid in expected],
                metadata={
                    "protocol_version": PROTOCOL_VERSION,
                    "generator_version": "controlled-v1",
                    "cell_id": cell.cell_id,
                    "family_id": family_id,
                    "pair_id": pair_id,
                    "case_uid": case_uid,
                    "pattern_id": cell.pattern_id,
                    "purpose": plan.purpose,
                    "series_id": cell.series_id,
                    "series_kind": cell.series_kind,
                    "seed": seed,
                    "pair_index": index,
                    "total_rules": cell.n,
                    "construction_rule_count": construction_count,
                    "independent_noise_count": noise_count,
                    "rule_correspondence": correspondence,
                },
            )
        )
    return cases[0], cases[1]
