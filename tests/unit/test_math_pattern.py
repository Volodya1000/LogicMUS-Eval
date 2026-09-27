import random

from logicmus_eval.enums import TemplatePackId
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.patterns.math import MathPatternStrategy
from logicmus_eval.verifier import verify_case


def test_math_pattern_strategy_unsat_cycle():
    strategy = MathPatternStrategy()
    rng = random.Random(42)
    core_vars = ["V1", "V2", "V3"]
    mapping = {"V1": "alpha", "V2": "beta", "V3": "gamma"}

    result = strategy.generate_pattern(
        mus_size=3,
        is_satisfiable=False,
        core_variables=core_vars,
        predicate_mapping=mapping,
        pack_id=TemplatePackId.MATH_PACK,
        rng=rng,
    )

    assert len(result.core_rules) == 3
    assert result.expected_mus_ids == ["R1", "R2", "R3"]

    case = LogicTestCase(
        case_id="math_unsat_3",
        mus_size=3,
        is_satisfiable=False,
        template_pack_id=TemplatePackId.MATH_PACK,
        predicate_mapping=mapping,
        rules=result.core_rules,
        mus_expected=result.expected_mus_ids,
    )

    verification = verify_case(case)
    assert verification.is_sat_correct is True
    assert verification.is_mus_valid is True
    assert verification.is_mus_minimal is True


def test_math_pattern_strategy_sat_chain():
    strategy = MathPatternStrategy()
    rng = random.Random(42)
    core_vars = ["V1", "V2", "V3"]
    mapping = {"V1": "alpha", "V2": "beta", "V3": "gamma"}

    result = strategy.generate_pattern(
        mus_size=3,
        is_satisfiable=True,
        core_variables=core_vars,
        predicate_mapping=mapping,
        pack_id=TemplatePackId.MATH_PACK,
        rng=rng,
    )

    assert len(result.core_rules) == 3
    assert result.expected_mus_ids == []

    case = LogicTestCase(
        case_id="math_sat_3",
        mus_size=3,
        is_satisfiable=True,
        template_pack_id=TemplatePackId.MATH_PACK,
        predicate_mapping=mapping,
        rules=result.core_rules,
        mus_expected=[],
    )

    verification = verify_case(case)
    assert verification.is_sat_correct is True


def test_math_pattern_multiple_mus_sizes():
    strategy = MathPatternStrategy()
    for size in (2, 3, 4, 5):
        core_vars = [f"V{i}" for i in range(1, size + 1)]
        mapping = {v: f"pred_{v}" for v in core_vars}

        res_unsat = strategy.generate_pattern(
            mus_size=size,
            is_satisfiable=False,
            core_variables=core_vars,
            predicate_mapping=mapping,
            pack_id=TemplatePackId.MATH_PACK,
            rng=random.Random(size),
        )
        case_unsat = LogicTestCase(
            case_id=f"unsat_{size}",
            mus_size=size,
            is_satisfiable=False,
            template_pack_id=TemplatePackId.MATH_PACK,
            predicate_mapping=mapping,
            rules=res_unsat.core_rules,
            mus_expected=res_unsat.expected_mus_ids,
        )
        ver_unsat = verify_case(case_unsat)
        assert ver_unsat.is_sat_correct is True
        assert ver_unsat.is_mus_valid is True
        assert ver_unsat.is_mus_minimal is True

        res_sat = strategy.generate_pattern(
            mus_size=size,
            is_satisfiable=True,
            core_variables=core_vars,
            predicate_mapping=mapping,
            pack_id=TemplatePackId.MATH_PACK,
            rng=random.Random(size),
        )
        case_sat = LogicTestCase(
            case_id=f"sat_{size}",
            mus_size=size,
            is_satisfiable=True,
            template_pack_id=TemplatePackId.MATH_PACK,
            predicate_mapping=mapping,
            rules=res_sat.core_rules,
            mus_expected=[],
        )
        ver_sat = verify_case(case_sat)
        assert ver_sat.is_sat_correct is True
