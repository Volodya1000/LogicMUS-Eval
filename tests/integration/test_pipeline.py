from src.enums import TemplatePackId
from src.generator import BenchmarkGenerator
from src.patterns.chain import ChainPatternStrategy
from src.patterns.math import MathPatternStrategy
from src.patterns.merge import MergePatternStrategy
from src.verifier import verify_case


def test_chain_strategy_pipeline():
    strategy = ChainPatternStrategy()
    generator = BenchmarkGenerator(strategy=strategy, total_rules=5)

    sat_case, unsat_case = generator.generate_pair(mus_size=3, index_in_batch=1)

    sat_verification = verify_case(sat_case)
    unsat_verification = verify_case(unsat_case)

    assert sat_verification.is_sat_correct is True
    assert unsat_verification.is_sat_correct is True
    assert unsat_verification.is_mus_valid is True
    assert unsat_verification.is_mus_minimal is True


def test_merge_strategy_pipeline():
    strategy = MergePatternStrategy()
    generator = BenchmarkGenerator(strategy=strategy, total_rules=6)

    _sat_case, unsat_case = generator.generate_pair(mus_size=3, index_in_batch=2)

    unsat_verification = verify_case(unsat_case)
    assert unsat_verification.is_sat_correct is True
    assert unsat_verification.is_mus_valid is True


def test_math_strategy_pipeline():
    strategy = MathPatternStrategy()
    generator = BenchmarkGenerator(
        strategy=strategy,
        total_rules=8,
        base_seed=123,
        pack_id=TemplatePackId.MATH_PACK,
    )

    sat_case, unsat_case = generator.generate_pair(mus_size=4, index_in_batch=0)

    assert len(sat_case.rules) == 8
    assert len(unsat_case.rules) == 8

    sat_verification = verify_case(sat_case, numeric_as_real=True)
    unsat_verification = verify_case(unsat_case, numeric_as_real=True)

    assert sat_verification.is_sat_correct is True
    assert unsat_verification.is_sat_correct is True
    assert unsat_verification.is_mus_valid is True
    assert unsat_verification.is_mus_minimal is True

    sat_verification_int = verify_case(sat_case, numeric_as_real=False)
    unsat_verification_int = verify_case(unsat_case, numeric_as_real=False)

    assert sat_verification_int.is_sat_correct is True
    assert unsat_verification_int.is_sat_correct is True
    assert unsat_verification_int.is_mus_valid is True
    assert unsat_verification_int.is_mus_minimal is True
