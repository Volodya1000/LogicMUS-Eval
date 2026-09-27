import random

from src.enums import CaseStatus, OperatorType, RulePrefix, TemplatePackId
from src.models.rules import NoiseRule
from src.models.test_case import LogicTestCase
from src.patterns.base import BasePatternStrategy
from src.templates import (
    PREDICATE_POOL,
    TEMPLATES,
    get_template_pack_id,
    negate,
)

# Noise rules may reuse templates of any single-`{var}` operator so that
# terminal-style phrases ("Главное требование:") also appear among noise.
# Multi-placeholder operators (IMPLIES, AND_IMPLIES, OR_FACT) are excluded:
# they require 2-3 distinct variables, which noise rules do not carry.
_NOISE_POOL_OPERATORS: tuple[OperatorType, ...] = (
    OperatorType.FACT,
    OperatorType.TERMINAL,
    OperatorType.NOISE,
)


class BenchmarkGenerator:
    def __init__(
        self,
        strategy: BasePatternStrategy,
        total_rules: int = 20,
        base_seed: int = 42,
        pack_id: TemplatePackId | None = None,
    ) -> None:
        self._strategy = strategy
        self._total_rules = total_rules
        self._base_seed = base_seed
        self._pack_id = pack_id

    def generate_pair(
        self, mus_size: int, index_in_batch: int
    ) -> tuple[LogicTestCase, LogicTestCase]:
        case_seed = self._base_seed + mus_size * 1000 + index_in_batch
        pack_id = self._pack_id or get_template_pack_id(case_seed)

        core_variables = [f"{RulePrefix.CORE_VAR}{i}" for i in range(1, mus_size + 1)]
        num_distractor_candidates = max(0, self._total_rules - 1)
        distractor_variables = [
            f"{RulePrefix.NOISE_VAR}{i}"
            for i in range(1, num_distractor_candidates + 1)
        ]

        all_variables = core_variables + distractor_variables
        full_mapping = self._get_predicate_mapping(case_seed, all_variables)

        sat_case = self._generate_single(
            mus_size,
            True,
            index_in_batch,
            case_seed,
            pack_id,
            core_variables,
            distractor_variables,
            full_mapping,
        )
        unsat_case = self._generate_single(
            mus_size,
            False,
            index_in_batch,
            case_seed,
            pack_id,
            core_variables,
            distractor_variables,
            full_mapping,
        )

        return sat_case, unsat_case

    # pylint: disable=too-many-arguments, too-many-positional-arguments, too-many-locals
    def _generate_single(
        self,
        mus_size: int,
        is_satisfiable: bool,
        index_in_batch: int,
        case_seed: int,
        pack_id: TemplatePackId,
        core_variables: list[str],
        distractor_variables: list[str],
        full_mapping: dict[str, str],
    ) -> LogicTestCase:
        rng = random.Random(case_seed)

        pattern_result = self._strategy.generate_pattern(
            mus_size=mus_size,
            is_satisfiable=is_satisfiable,
            core_variables=core_variables,
            predicate_mapping=full_mapping,
            pack_id=pack_id,
            rng=rng,
        )

        noise_rules: list[NoiseRule] = []
        noise_template_pools = [
            TEMPLATES[pack_id][op]
            for op in _NOISE_POOL_OPERATORS
            if op in TEMPLATES[pack_id]
        ]
        # Flatten to a single pool: template selection becomes a uniform draw
        # over all eligible noise-compatible phrases.
        noise_templates_flat = [tmpl for pool in noise_template_pools for tmpl in pool]

        num_core_rules = len(pattern_result.core_rules)
        num_distractors = max(0, self._total_rules - num_core_rules)

        for idx in range(num_distractors):
            u_var = distractor_variables[idx]
            rule_id = f"{RulePrefix.NOISE_RULE}{idx + 1}"
            noise_pol = rng.random() > 0.5
            noise_pred = full_mapping[u_var]
            wrapped = noise_pred if noise_pol else negate(noise_pred)
            noise_template = rng.choice(noise_templates_flat)
            noise_text = noise_template.replace("{var}", wrapped)

            noise_rules.append(
                NoiseRule(
                    id=rule_id,
                    text=noise_text,
                    variable=u_var,
                    predicate=noise_pred,
                    polarity=noise_pol,
                )
            )

        # SAT-balance guard: on short cases the terminal-only negation in UNSAT
        # was statistically visible. This is a defensive guard (fires rarely);
        # a stronger policy is scheduled for a follow-up iteration if leakage
        # stays above target.
        if is_satisfiable and noise_rules and all(r.polarity for r in noise_rules):
            first = noise_rules[0]
            noise_rules[0] = NoiseRule(
                id=first.id,
                text=first.text.replace(first.predicate, negate(first.predicate), 1),
                variable=first.variable,
                predicate=first.predicate,
                polarity=False,
            )

        all_rules = pattern_result.core_rules + noise_rules
        rng.shuffle(all_rules)

        status_str = CaseStatus.SAT.value if is_satisfiable else CaseStatus.UNSAT.value
        case_id = f"mus{mus_size}_{status_str}_{index_in_batch:03d}"

        return LogicTestCase(
            case_id=case_id,
            mus_size=mus_size,
            is_satisfiable=is_satisfiable,
            template_pack_id=pack_id,
            predicate_mapping=full_mapping,
            rules=all_rules,
            mus_expected=pattern_result.expected_mus_ids,
            metadata={"case_seed": case_seed},
        )

    def _get_predicate_mapping(
        self, case_seed: int, variables: list[str]
    ) -> dict[str, str]:
        rng = random.Random(case_seed)
        if len(variables) > len(PREDICATE_POOL):
            raise ValueError(
                f"Requested {len(variables)} unique predicates, "
                f"but pool only has {len(PREDICATE_POOL)}"
            )
        sampled_predicates = rng.sample(PREDICATE_POOL, len(variables))
        return dict(zip(variables, sampled_predicates))
