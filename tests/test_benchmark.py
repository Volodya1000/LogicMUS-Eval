from src.models import FactRule, ImpliesRule, LogicTestCase, TemplatePackId
from src.verifier import LogicVerifier


def test_satisfiable_case_verification():
    case = LogicTestCase(
        case_id="test_sat_1",
        k=2,
        is_satisfiable=True,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={"v1": "p1", "v2": "p2"},
        rules=[
            FactRule(
                id="r1",
                text="Fact 1",
                variable="v1",
                predicate="p1",
                polarity=True,
                is_fact=True,
            ),
            ImpliesRule(
                id="r2",
                text="Implies 1",
                antecedent="v1",
                consequent="v2",
                antecedent_predicate="p1",
                consequent_predicate="p2",
                antecedent_polarity=True,
                consequent_polarity=True,
            ),
        ],
        mus_expected=[],
        metadata={},
    )
    is_sat_correct, _, _, _ = LogicVerifier.verify_case(case)
    assert is_sat_correct is True


def test_unsatisfiable_case_verification():
    case = LogicTestCase(
        case_id="test_unsat_1",
        k=2,
        is_satisfiable=False,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={"v1": "p1"},
        rules=[
            FactRule(
                id="r1",
                text="Fact 1",
                variable="v1",
                predicate="p1",
                polarity=True,
                is_fact=True,
            ),
            FactRule(
                id="r2",
                text="Fact 2 negative",
                variable="v1",
                predicate="p1",
                polarity=False,
                is_fact=False,
            ),
        ],
        mus_expected=["r1", "r2"],
        metadata={},
    )
    is_sat_correct, mus_valid, mus_minimal, core = LogicVerifier.verify_case(case)
    assert is_sat_correct is True
    assert mus_valid is True
    assert mus_minimal is True
    assert sorted(core) == ["r1", "r2"]
