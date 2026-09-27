import z3  # type: ignore

from src.enums import TemplatePackId
from src.generator import BenchmarkGenerator
from src.models.rules import FactRule, NumericEQRule, NumericGTRule
from src.models.test_case import LogicTestCase
from src.patterns.chain import ChainPatternStrategy
from src.verifier import (
    build_z3_solver,
    check_minimality,
    extract_unsat_core,
    verify_case,
    verify_mus_uniqueness_by_structure,
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
        mus_expected=[],
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
        mus_expected=["R1", "R2"],
    )
    result = verify_case(case)
    assert result.is_sat_correct is True
    assert result.is_mus_valid is True
    assert result.is_mus_minimal is True


def test_numeric_cycle_verification_real():
    r1 = NumericGTRule(
        id="R1",
        text="",
        left_var="A",
        right_var="B",
        left_predicate="a",
        right_predicate="b",
    )
    r2 = NumericGTRule(
        id="R2",
        text="",
        left_var="B",
        right_var="C",
        left_predicate="b",
        right_predicate="c",
    )
    r3 = NumericGTRule(
        id="R3",
        text="",
        left_var="C",
        right_var="A",
        left_predicate="c",
        right_predicate="a",
    )

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
    r1 = NumericGTRule(
        id="R1",
        text="",
        left_var="A",
        right_var="B",
        left_predicate="a",
        right_predicate="b",
    )
    r2 = NumericGTRule(
        id="R2",
        text="",
        left_var="B",
        right_var="A",
        left_predicate="b",
        right_predicate="a",
    )

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
    r1 = NumericGTRule(
        id="R1",
        text="",
        left_var="A",
        right_var="B",
        left_predicate="a",
        right_predicate="b",
    )
    r2 = NumericEQRule(
        id="R2",
        text="",
        left_var="A",
        right_var="B",
        left_predicate="a",
        right_predicate="b",
    )

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


# ---------------------------------------------------------------------------
# verify_mus_uniqueness_by_structure
# ---------------------------------------------------------------------------


def test_mus_uniqueness_sat_case_returns_true():
    """SAT case: function must short-circuit before touching rule structure.

    Rationale: for a SAT case, uniqueness of MUS is vacuously true — there
    is no MUS. The early return protects callers from the "empty
    mus_expected" branch below, which returns False for UNSAT cases only.
    """
    r1 = FactRule(id="R1", text="", variable="p1", predicate="P", polarity=True)
    case = LogicTestCase(
        case_id="SAT_trivial",
        mus_size=1,
        is_satisfiable=True,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={"p1": "P"},
        rules=[r1],
        mus_expected=[],
    )
    assert verify_mus_uniqueness_by_structure(case) is True


def test_mus_uniqueness_empty_expected_returns_false():
    """UNSAT case with empty mus_expected: cannot prove uniqueness.

    An UNSAT case that declares no MUS is malformed — there must be at
    least one contradictory subset. Returning False makes the caller log
    a warning rather than silently accepting a broken case.
    """
    r1 = FactRule(id="R1", text="", variable="p1", predicate="P", polarity=True)
    r2 = FactRule(id="R2", text="", variable="p1", predicate="P", polarity=False)
    case = LogicTestCase(
        case_id="UNSAT_no_mus",
        mus_size=2,
        is_satisfiable=False,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={"p1": "P"},
        rules=[r1, r2],
        mus_expected=[],
    )
    assert verify_mus_uniqueness_by_structure(case) is False


def test_mus_uniqueness_rule_without_id_returns_false():
    """Malformed rule (missing id) must fail the check loudly.

    In practice ``BaseRule`` requires ``id``, so this branch is defensive.
    It exists so that a future rule type that forgets to set ``id`` does
    not silently pass the uniqueness gate.
    """
    r1 = FactRule(id="R1", text="", variable="p1", predicate="P", polarity=True)
    r2 = FactRule(id="R2", text="", variable="p1", predicate="P", polarity=False)
    # Simulate a rule whose `id` attribute is missing entirely — bypass
    # pydantic by constructing a plain object with the right shape.
    broken = type("BrokenRule", (), {"variable": "p2"})()
    case = LogicTestCase(
        case_id="UNSAT_broken_rule",
        mus_size=2,
        is_satisfiable=False,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={"p1": "P", "p2": "Q"},
        rules=[r1, r2, broken],
        mus_expected=["R1", "R2"],
    )
    assert verify_mus_uniqueness_by_structure(case) is False


def test_mus_uniqueness_disjoint_variables_returns_true():
    """Canonical well-formed case: core and noise share no variables.

    Core:  R1 (p1), R2 (not p1)              — variables {p1}
    Noise: R3 (p2), R4 (not p2)              — variables {p2}

    ``p1`` and ``p2`` are disjoint, so the structural proof holds. This
    mirrors what the generator produces after neutral renumbering.
    """
    r1 = FactRule(id="R1", text="", variable="p1", predicate="P", polarity=True)
    r2 = FactRule(id="R2", text="", variable="p1", predicate="P", polarity=False)
    r3 = FactRule(id="R3", text="", variable="p2", predicate="Q", polarity=True)
    r4 = FactRule(id="R4", text="", variable="p2", predicate="Q", polarity=False)
    case = LogicTestCase(
        case_id="UNSAT_disjoint",
        mus_size=2,
        is_satisfiable=False,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={"p1": "P", "p2": "Q"},
        rules=[r1, r2, r3, r4],
        mus_expected=["R1", "R2"],
    )
    assert verify_mus_uniqueness_by_structure(case) is True


def test_mus_uniqueness_overlapping_variables_returns_false():
    """Core and noise share a variable — the structural proof does not hold.

    Here a noise rule ``R3`` also mentions ``p1``. This is NOT allowed by
    the generator design (noise rules only touch their own distractor
    variables), but a hand-crafted or externally-loaded dataset could
    produce such a case. The function must reject it — reporting a
    non-unique MUS is safer than silently claiming uniqueness.
    """
    r1 = FactRule(id="R1", text="", variable="p1", predicate="P", polarity=True)
    r2 = FactRule(id="R2", text="", variable="p1", predicate="P", polarity=False)
    # Noise rule that (incorrectly, for this dataset) touches core variable p1.
    r3 = FactRule(id="R3", text="", variable="p1", predicate="P", polarity=True)
    case = LogicTestCase(
        case_id="UNSAT_overlap",
        mus_size=2,
        is_satisfiable=False,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={"p1": "P"},
        rules=[r1, r2, r3],
        mus_expected=["R1", "R2"],
    )
    assert verify_mus_uniqueness_by_structure(case) is False


def test_mus_uniqueness_dict_rules_supported():
    """Deserialization path: rules come back as plain dicts from JSONL.

    ``LogicTestCase.rules`` is typed as ``list[Any]`` precisely because
    ``storage.load_dataset`` yields dicts. The structural check must
    handle both representations identically.
    """
    rules = [
        {"id": "R1", "text": "", "variable": "p1", "operator_type": "FACT"},
        {"id": "R2", "text": "", "variable": "p1", "operator_type": "FACT"},
        {"id": "R3", "text": "", "variable": "p2", "operator_type": "FACT"},
    ]
    case = LogicTestCase(
        case_id="UNSAT_dicts",
        mus_size=2,
        is_satisfiable=False,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={"p1": "P", "p2": "Q"},
        rules=rules,
        mus_expected=["R1", "R2"],
    )
    assert verify_mus_uniqueness_by_structure(case) is True


def test_mus_uniqueness_real_generator_case():
    """End-to-end sanity: a real case from the generator passes the check.

    This is the integration-grade assertion. If the generator ever starts
    emitting cases where core and noise share variables, this test will
    fail before the smoke pipeline does.
    """
    strategy = ChainPatternStrategy()
    generator = BenchmarkGenerator(strategy=strategy, total_rules=10, base_seed=42)
    _sat_case, unsat_case = generator.generate_pair(mus_size=4, index_in_batch=0)

    assert unsat_case.is_satisfiable is False
    assert len(unsat_case.mus_expected) == 5  # mus_size=4 → 4 implicits + 1 terminal

    assert verify_mus_uniqueness_by_structure(unsat_case) is True
    # Cross-check with the existing verifier: MUS must also be valid & minimal.
    verification = verify_case(unsat_case)
    assert verification.is_sat_correct is True
    assert verification.is_mus_valid is True
    assert verification.is_mus_minimal is True
