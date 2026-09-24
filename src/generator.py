import random

from src.enums import OperatorType
from src.models import (
    FactRule,
    ImpliesRule,
    LogicTestCase,
    NoiseRule,
    Rule,
    TerminalRule,
)
from src.templates import PREDICATE_POOL, TEMPLATES, get_template_pack_id


class BenchmarkGenerator:
    def __init__(self, base_seed: int = 42) -> None:
        self.base_seed = base_seed

    def generate_pair(
        self, k: int, index_in_batch: int
    ) -> tuple[LogicTestCase, LogicTestCase]:
        pair_seed = self.base_seed + k * 1000 + index_in_batch
        pack_id = get_template_pack_id(pair_seed)

        vars_list = [f"v{i}" for i in range(1, k + 1)]
        noise_count = 20 - k
        noise_vars = [f"u{i}" for i in range(1, noise_count + 1)]

        all_variables = vars_list + noise_vars
        full_mapping = self._get_predicate_mapping(pair_seed, all_variables)

        if len(set(full_mapping.values())) != len(full_mapping):
            raise ValueError("Predicate mapping is not bijective")

        pred_map = {v: full_mapping[v] for v in vars_list}
        noise_pred_map = {u: full_mapping[u] for u in noise_vars}

        noise_rng = random.Random(f"noise:{pair_seed}")
        noise_polarities = [noise_rng.random() > 0.5 for _ in range(noise_count)]

        sat_case = self._generate_single(
            k=k,
            is_sat=True,
            index_in_batch=index_in_batch,
            pair_seed=pair_seed,
            pack_id=pack_id,
            vars_list=vars_list,
            noise_vars=noise_vars,
            pred_map=pred_map,
            noise_pred_map=noise_pred_map,
            full_mapping=full_mapping,
            noise_polarities=noise_polarities,
        )

        unsat_case = self._generate_single(
            k=k,
            is_sat=False,
            index_in_batch=index_in_batch,
            pair_seed=pair_seed,
            pack_id=pack_id,
            vars_list=vars_list,
            noise_vars=noise_vars,
            pred_map=pred_map,
            noise_pred_map=noise_pred_map,
            full_mapping=full_mapping,
            noise_polarities=noise_polarities,
        )

        return sat_case, unsat_case

    def _generate_single(
        self,
        k: int,
        is_sat: bool,
        index_in_batch: int,
        pair_seed: int,
        pack_id: str,
        vars_list: list[str],
        noise_vars: list[str],
        pred_map: dict[str, str],
        noise_pred_map: dict[str, str],
        full_mapping: dict[str, str],
        noise_polarities: list[bool],
    ) -> LogicTestCase:
        pack_templates = TEMPLATES[pack_id]
        core_rules: list[Rule] = []

        fact_positive = True if not is_sat else (pair_seed % 2 == 0)
        local_template_rng = random.Random(f"template:{pair_seed}")

        fact_template = local_template_rng.choice(pack_templates[OperatorType.FACT])
        fact_pred = pred_map[vars_list[0]]
        fact_text = fact_template.format(
            var=("" if fact_positive else "отсутствие ") + fact_pred
        )

        core_rules.append(
            FactRule(
                id="r1",
                text=fact_text,
                variable=vars_list[0],
                predicate=fact_pred,
                polarity=fact_positive,
            )
        )

        for i in range(len(vars_list) - 1):
            v_curr = vars_list[i]
            v_next = vars_list[i + 1]

            implies_template = local_template_rng.choice(
                pack_templates[OperatorType.IMPLIES]
            )
            ant_pred = pred_map[v_curr]
            cons_pred = pred_map[v_next]
            implies_text = implies_template.format(ant=ant_pred, cons=cons_pred)

            core_rules.append(
                ImpliesRule(
                    id=f"r{i + 2}",
                    text=implies_text,
                    antecedent=v_curr,
                    consequent=v_next,
                    antecedent_predicate=ant_pred,
                    consequent_predicate=cons_pred,
                    antecedent_polarity=True,
                    consequent_polarity=True,
                )
            )

        last_var = vars_list[-1]
        term_id = f"r{len(core_rules) + 1}"
        term_polarity = fact_positive if is_sat else False

        term_template = local_template_rng.choice(pack_templates[OperatorType.TERMINAL])
        term_pred = pred_map[last_var]
        term_text = term_template.format(var=term_pred)

        core_rules.append(
            TerminalRule(
                id=term_id,
                text=term_text,
                variable=last_var,
                predicate=term_pred,
                polarity=term_polarity,
            )
        )

        mus_expected = [r.id for r in core_rules] if not is_sat else []

        noise_rules: list[Rule] = []
        for idx, u_var in enumerate(noise_vars):
            rule_id = f"n{idx + 1}"
            noise_pol = noise_polarities[idx]
            noise_template = local_template_rng.choice(
                pack_templates[OperatorType.NOISE]
            )
            noise_pred = noise_pred_map[u_var]
            noise_text = noise_template.format(
                var=("" if noise_pol else "отсутствие ") + noise_pred
            )

            noise_rules.append(
                NoiseRule(
                    id=rule_id,
                    text=noise_text,
                    variable=u_var,
                    predicate=noise_pred,
                    polarity=noise_pol,
                )
            )

        all_rules: list[Rule] = core_rules + noise_rules
        local_order_rng = random.Random(f"order:{pair_seed}")
        local_order_rng.shuffle(all_rules)

        case_id = f"k{k}_{'sat' if is_sat else 'unsat'}_{index_in_batch:03d}"
        return LogicTestCase(
            case_id=case_id,
            k=k,
            is_satisfiable=is_sat,
            template_pack_id=pack_id,
            predicate_mapping=full_mapping,
            rules=all_rules,
            mus_expected=mus_expected,
            metadata={"pair_seed": pair_seed, "is_satisfiable": is_sat},
        )

    def _get_predicate_mapping(
        self, pair_seed: int, variables: list[str]
    ) -> dict[str, str]:
        rng = random.Random(f"unified_predicates_{pair_seed}")
        pool = PREDICATE_POOL.copy()
        rng.shuffle(pool)
        return {var: pool[i % len(pool)] for i, var in enumerate(variables)}
