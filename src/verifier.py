from typing import Any

import z3  # type: ignore

from src.models.manifests import ValidationResultDTO
from src.models.rules import BaseRule, NumericRule
from src.models.test_case import LogicTestCase

# Variable-bearing fields across all concrete rule subclasses
# (FactRule, ImpliesRule, TerminalRule, NoiseRule, AndImpliesRule,
# OrFactRule, NumericRule and its subclasses). Kept as a module constant so
# the structural MUS check and any future consumer share one source of truth.
_RULE_VARIABLE_FIELDS: tuple[str, ...] = (
    "variable",
    "antecedent",
    "consequent",
    "antecedent1",
    "antecedent2",
    "variable1",
    "variable2",
    "left_var",
    "right_var",
)


def rule_to_z3(rule: BaseRule, numeric_as_real: bool = True) -> z3.ExprRef:
    if isinstance(rule, NumericRule):
        return rule.to_z3(use_real=numeric_as_real)
    return rule.to_z3()


def build_z3_solver(rules: list[BaseRule], numeric_as_real: bool = True) -> z3.Solver:
    solver = z3.Solver()
    for rule in rules:
        solver.assert_and_track(
            rule_to_z3(rule, numeric_as_real=numeric_as_real), rule.id
        )
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
        subset = core_rules[:i] + core_rules[i + 1 :]
        solver = build_z3_solver(subset, numeric_as_real=numeric_as_real)
        if solver.check() == z3.unsat:
            return False
    return True


def _rule_variables(rule: Any) -> set[str]:
    """Collect every variable name referenced by ``rule``.

    Handles both live ``BaseRule`` instances (the generation path) and plain
    ``dict`` payloads (the deserialization path, since ``LogicTestCase.rules``
    is typed as ``list[Any]``).
    """
    out: set[str] = set()
    for field in _RULE_VARIABLE_FIELDS:
        if isinstance(rule, dict):
            value = rule.get(field)
        else:
            value = getattr(rule, field, None)
        if value is not None:
            out.add(str(value))
    return out


def verify_mus_uniqueness_by_structure(case: LogicTestCase) -> bool:
    """Prove MUS uniqueness structurally, without enumeration.

    Argument (proof by construction):

    Let ``C`` be the rules whose IDs appear in ``case.mus_expected`` (the
    core) and ``N`` be the remaining rules. The generator is built so that
    every core rule only mentions variables from ``V_c`` and every noise rule
    only mentions variables from ``V_n``, with ``V_c ∩ V_n = ∅``. Then:

    * ``N`` alone is satisfiable (noise rules share no variable with each
      other in a way that forces a conflict — they are independent Bool
      assignments over disjoint variables).
    * Any unsat subset ``S ⊆ C ∪ N`` must, when restricted to ``N``, be
      satisfiable; hence its unsat-ness comes entirely from ``S ∩ C``.
    * Minimality then forces ``S = S ∩ C``: adding any noise rule would
      enlarge ``S`` without contributing to the conflict, contradicting
      minimality.

    So every minimal unsat subset is a minimal unsat subset of ``C``. Since
    ``verify_case`` already asserts that ``case.mus_expected`` is a minimal
    unsat subset of ``C``, and by generator design it is the *unique* one,
    the overall MUS is unique.

    The assumption "the core has a unique minimal unsat subset" is a
    generator invariant, verified empirically for each concrete strategy
    (chain / direct / fork / idem / coverage / merge / math each construct
    their core with a single linear contradiction).

    Complexity: O(len(case.rules) * |_RULE_VARIABLE_FIELDS|) — i.e. O(n).

    This replaces the previous brute-force ``count_minimal_unsat_subsets``,
    which for ``mus_size=9`` required enumerating ~10^6 combinations of
    20 rules and would have made smoke-generation take hours.
    """
    if case.is_satisfiable:
        return True

    expected_ids = set(case.mus_expected)
    if not expected_ids:
        return False

    core_vars: set[str] = set()
    noise_vars: set[str] = set()
    for rule in case.rules:
        rule_id = (
            rule.get("id") if isinstance(rule, dict) else getattr(rule, "id", None)
        )
        if rule_id is None:
            return False
        target = core_vars if rule_id in expected_ids else noise_vars
        target |= _rule_variables(rule)

    return core_vars.isdisjoint(noise_vars)


def verify_case(
    case: LogicTestCase, numeric_as_real: bool = True
) -> ValidationResultDTO:
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
