import z3  # type: ignore

from src.enums import TemplatePackId
from src.models.rules import FactRule, NumericEQRule, NumericGTRule
from src.models.test_case import LogicTestCase
from src.verifier import (
    build_z3_solver,
    check_minimality,
    extract_unsat_core,
    verify_case,
)


def test_build_z3_solver():
    r1 = FactRule(id="R1", text="", variable="A", predicate="P", polarity=True)
    solver = build_z3_solver([r1])
    assert solver.check() == z3.sat


def test_extract_unsat_core():
    r1 = FactRule(id="R1", text="", variable="A", predicate="P", polarity=True)
    r2 = FactRule(id="R2", text="", variable="A", predicate="P", polarity=False)
    solver = build_z3_solver([r1, r2])
    assert solver.check() == z3.unsat
    core = extract_unsat_core(solver)
    assert set(core) == {"R1", "R2"}


def test_check_minimality():
    r1 = FactRule(id="R1", text="", variable="A", predicate="P", polarity=True)
    r2 = FactRule(id="R2", text="", variable="A", predicate="P", polarity=False)
    r3 = FactRule(id="R3", text="", variable="B", predicate="Q", polarity=True)

    assert check_minimality([r1, r2, r3], ["R1", "R2"]) is True
    assert check_minimality([r1, r2, r3], ["R1", "R2", "R3"]) is False


def test_verify_case_sat():
    r1 = FactRule(id="R1", text="", variable="A", predicate="P", polarity=True)
    case = LogicTestCase(
        case_id="C1",
        mus_size=1,
        is_satisfiable=True,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={"A": "P"},
        rules=[r1],
        mus_expected=[]
    )
    result = verify_case(case)
    assert result.is_sat_correct is True
    assert result.is_mus_valid is True


def test_verify_case_unsat():
    r1 = FactRule(id="R1", text="", variable="A", predicate="P", polarity=True)
    r2 = FactRule(id="R2", text="", variable="A", predicate="P", polarity=False)
    case = LogicTestCase(
        case_id="C2",
        mus_size=2,
        is_satisfiable=False,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={"A": "P"},
        rules=[r1, r2],
        mus_expected=["R1", "R2"]
    )
    result = verify_case(case)
    assert result.is_sat_correct is True
    assert result.is_mus_valid is True
    assert result.is_mus_minimal is True


def test_numeric_cycle_verification_real():
    r1 = NumericGTRule(id="R1", text="", left_var="A", right_var="B", left_predicate="a", right_predicate="b")
    r2 = NumericGTRule(id="R2", text="", left_var="B", right_var="C", left_predicate="b", right_predicate="c")
    r3 = NumericGTRule(id="R3", text="", left_var="C", right_var="A", left_predicate="c", right_predicate="a")

    case = LogicTestCase(
        case_id="M_UNSAT_3",
        mus_size=3,
        is_satisfiable=False,
        template_pack_id=TemplatePackId.MATH_PACK,
        predicate_mapping={"A": "a", "B": "b", "C": "c"},
        rules=[r1, r2, r3],
        mus_expected=["R1", "R2", "R3"],
    )

    result = verify_case(case, numeric_as_real=True)
    assert result.is_sat_correct is True
    assert result.is_mus_valid is True
    assert result.is_mus_minimal is True


def test_numeric_cycle_verification_int():
    r1 = NumericGTRule(id="R1", text="", left_var="A", right_var="B", left_predicate="a", right_predicate="b")
    r2 = NumericGTRule(id="R2", text="", left_var="B", right_var="A", left_predicate="b", right_predicate="a")

    case = LogicTestCase(
        case_id="M_UNSAT_2",
        mus_size=2,
        is_satisfiable=False,
        template_pack_id=TemplatePackId.MATH_PACK,
        predicate_mapping={"A": "a", "B": "b"},
        rules=[r1, r2],
        mus_expected=["R1", "R2"],
    )

    result = verify_case(case, numeric_as_real=False)
    assert result.is_sat_correct is True
    assert result.is_mus_valid is True
    assert result.is_mus_minimal is True


def test_numeric_equality_contradiction():
    r1 = NumericGTRule(id="R1", text="", left_var="A", right_var="B", left_predicate="a", right_predicate="b")
    r2 = NumericEQRule(id="R2", text="", left_var="A", right_var="B", left_predicate="a", right_predicate="b")

    case = LogicTestCase(
        case_id="M_EQ_UNSAT",
        mus_size=2,
        is_satisfiable=False,
        template_pack_id=TemplatePackId.MATH_PACK,
        predicate_mapping={"A": "a", "B": "b"},
        rules=[r1, r2],
        mus_expected=["R1", "R2"],
    )

    result = verify_case(case, numeric_as_real=True)
    assert result.is_sat_correct is True
    assert result.is_mus_valid is True
    assert result.is_mus_minimal is True
