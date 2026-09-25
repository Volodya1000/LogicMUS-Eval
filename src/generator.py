import random

from src.enums import CaseStatus, OperatorType, RulePrefix, TemplatePackId
from src.models.rules import BaseRule, NoiseRule
from src.models.test_case import LogicTestCase
from src.patterns.base import BasePatternStrategy
from src.templates import PREDICATE_POOL, TEMPLATES, get_template_pack_id


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

        distractor_variables = [
            f"{RulePrefix.NOISE_VAR}{i}" for i in range(1, self._total_rules + 1)
        ]

        all_variables = core_variables + distractor_variables
        full_mapping = self._get_predicate_mapping(case_seed, all_variables)

        sat_case = self._generate_single(
            mus_size, True, index_in_batch, case_seed, pack_id,
            core_variables, distractor_variables, full_mapping
        )
        unsat_case = self._generate_single(
            mus_size, False, index_in_batch, case_seed, pack_id,
            core_variables, distractor_variables, full_mapping
        )

        return sat_case, unsat_case

    # pylint: disable=too-many-arguments, too-many-positional-arguments, too-many-locals
    def _generate_single(
            self, mus_size: int, is_satisfiable: bool, index_in_batch: int, case_seed: int,
            pack_id: TemplatePackId, core_variables: list[str], distractor_variables: list[str],
            full_mapping: dict[str, str]
    ) -> LogicTestCase:
        rng = random.Random(case_seed)

        pattern_result = self._strategy.generate_pattern(
            mus_size=mus_size, is_satisfiable=is_satisfiable,
            core_variables=core_variables, predicate_mapping=full_mapping,
            pack_id=pack_id, rng=rng
        )

        noise_rules: list[BaseRule] = []
        noise_templates = TEMPLATES[pack_id][OperatorType.NOISE]

        num_core_rules = len(pattern_result.core_rules)
        num_distractors = max(0, self._total_rules - num_core_rules)

        for idx in range(num_distractors):
            u_var = distractor_variables[idx]
            rule_id = f"{RulePrefix.NOISE_RULE}{idx + 1}"
            noise_pol = rng.random() > 0.5
            noise_pred = full_mapping[u_var]
            noise_template = rng.choice(noise_templates)

            prefix_not = "" if noise_pol else "not "
            noise_text = noise_template.replace("{var}", f"{prefix_not}{noise_pred}")

            noise_rules.append(NoiseRule(
                id=rule_id, text=noise_text, variable=u_var,
                predicate=noise_pred, polarity=noise_pol
            ))

        all_rules = pattern_result.core_rules + noise_rules
        rng.shuffle(all_rules)

        status_str = CaseStatus.SAT.value if is_satisfiable else CaseStatus.UNSAT.value
        case_id = f"mus{mus_size}_{status_str}_{index_in_batch:03d}"

        return LogicTestCase(
            case_id=case_id, mus_size=mus_size, is_satisfiable=is_satisfiable,
            template_pack_id=pack_id, predicate_mapping=full_mapping,
            rules=all_rules, mus_expected=pattern_result.expected_mus_ids,
            metadata={"case_seed": case_seed}
        )

    def _get_predicate_mapping(self, case_seed: int, variables: list[str]) -> dict[str, str]:
        rng = random.Random(case_seed)
        pool = list(PREDICATE_POOL)
        rng.shuffle(pool)
        return {var: pool[i % len(pool)] for i, var in enumerate(variables)}
