import pytest
import z3

from logicmus_eval.generator import BenchmarkGenerator
from logicmus_eval.patterns.chain import ChainPatternStrategy
from logicmus_eval.patterns.coverage import CoveragePatternStrategy
from logicmus_eval.patterns.direct import DirectPatternStrategy
from logicmus_eval.patterns.fork import ForkPatternStrategy
from logicmus_eval.patterns.idem import IdemPatternStrategy
from logicmus_eval.patterns.math import MathPatternStrategy
from logicmus_eval.patterns.merge import MergePatternStrategy
from logicmus_eval.run_pipeline import GenerationConfig, generate_dataset
from logicmus_eval.verifier import build_z3_solver


@pytest.mark.parametrize("seed", [7, 42, 2026])
@pytest.mark.parametrize(
    "strategy,k,n",
    [
        (DirectPatternStrategy, 2, 2),
        (DirectPatternStrategy, 2, 10),
        (ChainPatternStrategy, 3, 3),
        (ChainPatternStrategy, 8, 12),
        (ForkPatternStrategy, 3, 4),
        (CoveragePatternStrategy, 3, 3),
        (IdemPatternStrategy, 3, 3),
        (MergePatternStrategy, 4, 4),
        (MathPatternStrategy, 2, 2),
        (MathPatternStrategy, 7, 10),
    ],
)
def test_exact_k_and_unique_mus_for_every_topology(strategy, k, n, seed):
    generator = BenchmarkGenerator(
        strategy(), total_rules=n, base_seed=seed, pack_id=strategy.forced_pack_id
    )
    sat, unsat = generator.generate_pair(k, 0)
    assert len(sat.rules) == len(unsat.rules) == n
    assert sat.mus_expected == []
    assert len(set(unsat.mus_expected)) == k
    assert build_z3_solver(sat.rules).check() == z3.sat
    assert build_z3_solver(unsat.rules).check() == z3.unsat
    core = [r for r in unsat.rules if r.id in unsat.mus_expected]
    assert build_z3_solver(core).check() == z3.unsat
    # Removing any member from the WHOLE instance proves no second MUS exists.
    for rid in unsat.mus_expected:
        assert (
            build_z3_solver([r for r in unsat.rules if r.id != rid]).check() == z3.sat
        )
    assert sat.metadata["pattern_id"] == unsat.metadata["pattern_id"] == strategy.name
    assert sat.metadata["pair_id"] == unsat.metadata["pair_id"]
    assert sat.metadata["generator_version"] == 2


@pytest.mark.parametrize(
    "strategy,k",
    [
        (DirectPatternStrategy, 3),
        (ChainPatternStrategy, 2),
        (ForkPatternStrategy, 4),
        (CoveragePatternStrategy, 2),
        (IdemPatternStrategy, 2),
        (MergePatternStrategy, 3),
        (MathPatternStrategy, 1),
    ],
)
def test_unsupported_cardinality_is_rejected(strategy, k):
    with pytest.raises(ValueError, match="mus_size"):
        BenchmarkGenerator(strategy(), total_rules=10).generate_pair(k, 0)


def test_fork_requires_room_for_redundant_branch():
    with pytest.raises(ValueError, match="total_rules"):
        BenchmarkGenerator(ForkPatternStrategy(), total_rules=3).generate_pair(3, 0)


def test_grid_excludes_patterns_that_do_not_fit_n():
    dataset = generate_dataset(GenerationConfig([3], 12, 3, 42, "unused"))
    assert len(dataset) == 24
    assert all(len(c.rules) == 3 for c in dataset)
    assert all(c.metadata["pattern_id"] != "fork" for c in dataset)


@pytest.mark.parametrize(
    "sizes,pairs,n",
    [([], 1, 10), ([2, 2], 1, 10), ([0], 1, 10), ([2], 0, 10), ([3], 1, 2)],
)
def test_invalid_generation_config_fails_before_generation(sizes, pairs, n):
    with pytest.raises(ValueError):
        generate_dataset(GenerationConfig(sizes, pairs, n, 42, "unused"))
