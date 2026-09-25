from src.generator import BenchmarkGenerator
from src.patterns.chain import ChainPatternStrategy
from src.patterns.merge import MergePatternStrategy
from src.verifier import verify_case


def test_chain_strategy_pipeline():
    strategy = ChainPatternStrategy()
    generator = BenchmarkGenerator(strategy=strategy, total_rules_count=5)

    sat_case, unsat_case = generator.generate_pair(mus_size=3, index_in_batch=1)

    sat_verification = verify_case(sat_case)
    unsat_verification = verify_case(unsat_case)

    assert sat_verification.is_sat_correct is True
    assert unsat_verification.is_sat_correct is True
    assert unsat_verification.is_mus_valid is True
    assert unsat_verification.is_mus_minimal is True


def test_merge_strategy_pipeline():
    strategy = MergePatternStrategy()
    generator = BenchmarkGenerator(strategy=strategy, total_rules_count=6)

    _sat_case, unsat_case = generator.generate_pair(mus_size=3, index_in_batch=2)

    unsat_verification = verify_case(unsat_case)
    assert unsat_verification.is_sat_correct is True
    assert unsat_verification.is_mus_valid is True
