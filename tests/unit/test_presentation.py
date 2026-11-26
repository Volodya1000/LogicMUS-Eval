import pytest
import z3

from logicmus_eval.enums import TemplatePackId
from logicmus_eval.evaluation.strategies import (
    DirectEvaluationStrategy,
    Z3TranslationEvaluationStrategy,
)
from logicmus_eval.generator import BenchmarkGenerator
from logicmus_eval.models.rules import AndImpliesRule, OrFactRule
from logicmus_eval.patterns.chain import ChainPatternStrategy
from logicmus_eval.patterns.math import MathPatternStrategy


@pytest.mark.parametrize(
    "strategy", [DirectEvaluationStrategy, Z3TranslationEvaluationStrategy]
)
def test_model_input_is_independent_of_case_identity(strategy):
    _, case = BenchmarkGenerator(ChainPatternStrategy()).generate_pair(3, 0)
    changed = case.model_copy(update={"case_id": "secret_gold_SAT_answer"})
    assert strategy().build_prompt(case) == strategy().build_prompt(changed)
    assert case.case_id not in strategy().build_prompt(case)


def test_variable_names_do_not_identify_core_by_prefix():
    core_variables = set()
    for i in range(10):
        _, case = BenchmarkGenerator(
            ChainPatternStrategy(), total_rules=10
        ).generate_pair(3, i)
        core_variables.update(
            r.variable
            for r in case.rules
            if r.id in case.mus_expected and hasattr(r, "variable")
        )
    assert any(int(v[1:]) > 2 for v in core_variables)


def test_signed_and_implies_has_correct_truth_conditions():
    rule = AndImpliesRule(
        id="R1",
        text="",
        antecedent1="a",
        antecedent2="b",
        consequent="c",
        antecedent1_predicate="a",
        antecedent2_predicate="b",
        consequent_predicate="c",
        antecedent1_polarity=False,
        consequent_polarity=False,
    )
    solver = z3.Solver()
    solver.add(rule.to_z3(), z3.Not(z3.Bool("a")), z3.Bool("b"), z3.Bool("c"))
    assert solver.check() == z3.unsat


def test_signed_or_has_correct_truth_conditions():
    rule = OrFactRule(
        id="R1",
        text="",
        variable1="a",
        variable2="b",
        predicate1="a",
        predicate2="b",
        polarity1=False,
        polarity2=False,
    )
    solver = z3.Solver()
    solver.add(rule.to_z3(), z3.Bool("a"), z3.Bool("b"))
    assert solver.check() == z3.unsat


def test_numeric_prompt_declares_numeric_variables():
    _, case = BenchmarkGenerator(
        MathPatternStrategy(), total_rules=3, pack_id=TemplatePackId.MATH_PACK
    ).generate_pair(3, 0)
    prompt = Z3TranslationEvaluationStrategy().build_prompt(case)
    assert "Real('" in prompt
    assert "Bool('" not in prompt


def test_paired_generation_is_reproducible_and_has_no_english_negation():
    generator = BenchmarkGenerator(ChainPatternStrategy(), total_rules=10)
    sat, unsat = generator.generate_pair(4, 3)
    again = generator.generate_pair(4, 3)
    assert [c.model_dump() for c in (sat, unsat)] == [c.model_dump() for c in again]
    assert sat.predicate_mapping == unsat.predicate_mapping
    assert all("not " not in r.text for c in (sat, unsat) for r in c.rules)


def test_signed_rendering_matches_the_symbolic_literals():
    import random

    from logicmus_eval.generation_rendering import render_rule

    rule = AndImpliesRule(
        id="R1",
        text="",
        antecedent1="a",
        antecedent2="b",
        consequent="c",
        antecedent1_predicate="альфа",
        antecedent2_predicate="бета",
        consequent_predicate="гамма",
        antecedent1_polarity=False,
        consequent_polarity=False,
    )
    assert render_rule(rule, TemplatePackId.PACK_00, random.Random(1)) == (
        "Если неверно, что альфа и при этом бета, то неверно, что гамма."
    )
