import z3  # type: ignore

from src.models.rules import AndImpliesRule, FactRule


def test_fact_rule_to_z3():
    rule = FactRule(
        id="R1",
        text="A is true",
        variable="A",
        predicate="alpha",
        polarity=True
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
        consequent_predicate="gamma"
    )
    expr = rule.to_z3()
    assert z3.is_expr(expr)
