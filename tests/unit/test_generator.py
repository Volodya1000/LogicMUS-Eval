from logicmus_eval.generator import BenchmarkGenerator
from logicmus_eval.patterns.chain import ChainPatternStrategy
from logicmus_eval.verifier import verify_case


def test_generator_deterministic_behavior():
    strategy = ChainPatternStrategy()
    gen1 = BenchmarkGenerator(strategy=strategy, total_rules=10, base_seed=42)
    gen2 = BenchmarkGenerator(strategy=strategy, total_rules=10, base_seed=42)

    sat1, unsat1 = gen1.generate_pair(mus_size=3, index_in_batch=0)
    sat2, unsat2 = gen2.generate_pair(mus_size=3, index_in_batch=0)

    assert sat1.case_id == sat2.case_id
    assert sat1.rules[0].id == sat2.rules[0].id
    assert unsat1.mus_expected == unsat2.mus_expected


def test_generator_respects_total_rules_constraint():
    strategy = ChainPatternStrategy()
    gen = BenchmarkGenerator(strategy=strategy, total_rules=15, base_seed=42)
    sat, unsat = gen.generate_pair(mus_size=4, index_in_batch=1)

    assert len(sat.rules) == 15
    assert len(unsat.rules) == 15
    assert len(sat.mus_expected) == 0
    assert len(unsat.mus_expected) == 5


def test_generator_different_mus_size():
    strategy = ChainPatternStrategy()
    gen = BenchmarkGenerator(strategy=strategy, total_rules=10, base_seed=42)
    sat, _ = gen.generate_pair(mus_size=5, index_in_batch=0)

    core_rules = [r for r in sat.rules if not r.is_noise]
    noise_rules = [r for r in sat.rules if r.is_noise]

    assert len(core_rules) == 6
    assert len(noise_rules) == 4


def test_generated_cases_are_logically_valid():
    strategy = ChainPatternStrategy()
    gen = BenchmarkGenerator(strategy=strategy, total_rules=5, base_seed=99)
    sat, unsat = gen.generate_pair(mus_size=3, index_in_batch=0)

    sat_result = verify_case(sat)
    unsat_result = verify_case(unsat)

    assert sat_result.is_sat_correct is True
    assert unsat_result.is_sat_correct is True
    assert unsat_result.is_mus_valid is True
