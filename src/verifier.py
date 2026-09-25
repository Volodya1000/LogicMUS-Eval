import z3  # type: ignore

from src.models.manifests import ValidationResultDTO
from src.models.rules import BaseRule, NumericRule
from src.models.test_case import LogicTestCase


def rule_to_z3(rule: BaseRule, numeric_as_real: bool = True) -> z3.ExprRef:
    if isinstance(rule, NumericRule):
        return rule.to_z3(use_real=numeric_as_real)
    return rule.to_z3()


def build_z3_solver(rules: list[BaseRule], numeric_as_real: bool = True) -> z3.Solver:
    solver = z3.Solver()
    for rule in rules:
        solver.assert_and_track(rule_to_z3(rule, numeric_as_real=numeric_as_real), rule.id)
    return solver


def extract_unsat_core(solver: z3.Solver) -> list[str]:
    return [str(c) for c in solver.unsat_core()]


def check_minimality(
        rules: list[BaseRule], core_ids: list[str], numeric_as_real: bool = True
) -> bool:
    if not core_ids:
        return True
    core_rules = [r for r in rules if r.id in core_ids]

    for i in range(len(core_rules)):
        subset = core_rules[:i] + core_rules[i + 1:]
        solver = build_z3_solver(subset, numeric_as_real=numeric_as_real)
        if solver.check() == z3.unsat:
            return False
    return True


def verify_case(case: LogicTestCase, numeric_as_real: bool = True) -> ValidationResultDTO:
    solver = build_z3_solver(case.rules, numeric_as_real=numeric_as_real)
    result = solver.check()
    is_sat = result == z3.sat

    is_sat_correct = is_sat == case.is_satisfiable
    is_mus_valid = True
    is_mus_minimal = True
    extracted_core_ids: list[str] = []

    if not is_sat:
        extracted_core_ids = extract_unsat_core(solver)
        expected_set = set(case.mus_expected)
        actual_set = set(extracted_core_ids)
        is_mus_valid = expected_set == actual_set
        is_mus_minimal = check_minimality(
            case.rules, extracted_core_ids, numeric_as_real=numeric_as_real
        )

    return ValidationResultDTO(
        is_sat_correct=is_sat_correct,
        is_mus_valid=is_mus_valid,
        is_mus_minimal=is_mus_minimal,
        extracted_core_ids=extracted_core_ids,
    )
