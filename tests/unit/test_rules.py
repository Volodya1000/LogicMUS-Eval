import z3  # type: ignore

from src.models.rules import (
    AndImpliesRule,
    FactRule,
    NumericEQRule,
    NumericGTRule,
    NumericLTRule,
    NumericRule,
)


def test_fact_rule_to_z3():
    rule = FactRule(
        id="R1", text="A is true", variable="A", predicate="alpha", polarity=True
    )
    expr = rule.to_z3()
    assert z3.is_expr(expr)


def test_and_implies_rule_to_z3():
    rule = AndImpliesRule(
        id="R2",
        text="A and B implies C",
        antecedent1="A",
        antecedent2="B",
        consequent="C",
        antecedent1_predicate="alpha",
        antecedent2_predicate="beta",
        consequent_predicate="gamma",
    )
    expr = rule.to_z3()
    assert z3.is_expr(expr)


def test_numeric_gt_rule_to_z3():
    rule = NumericGTRule(
        id="R1",
        text="A > B",
        left_var="A",
        right_var="B",
        left_predicate="alpha",
        right_predicate="beta",
    )
    expr_real = rule.to_z3(use_real=True)
    expr_int = rule.to_z3(use_real=False)

    assert z3.is_expr(expr_real)
    assert z3.is_expr(expr_int)

    solver = z3.Solver()
    solver.add(expr_real)
    solver.add(z3.Real("A") == 5, z3.Real("B") == 3)
    assert solver.check() == z3.sat


def test_numeric_lt_rule_to_z3():
    rule = NumericLTRule(
        id="R2",
        text="A < B",
        left_var="A",
        right_var="B",
        left_predicate="alpha",
        right_predicate="beta",
    )
    solver = z3.Solver()
    solver.add(rule.to_z3())
    solver.add(z3.Real("A") == 10, z3.Real("B") == 2)
    assert solver.check() == z3.unsat


def test_numeric_eq_rule_to_z3():
    rule = NumericEQRule(
        id="R3",
        text="A == B",
        left_var="A",
        right_var="B",
        left_predicate="alpha",
        right_predicate="beta",
    )
    solver = z3.Solver()
    solver.add(rule.to_z3())
    solver.add(z3.Real("A") == 4, z3.Real("B") == 4)
    assert solver.check() == z3.sat


def test_generic_numeric_rule():
    rule = NumericRule(
        id="R4",
        text="A > B",
        left_var="A",
        right_var="B",
        operator=">",
        left_predicate="alpha",
        right_predicate="beta",
    )
    assert rule.operator == ">"
    assert z3.is_expr(rule.to_z3())
