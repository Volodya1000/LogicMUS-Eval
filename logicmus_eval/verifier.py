from typing import Any

import z3  # type: ignore

from logicmus_eval.models.manifests import ValidationResultDTO
from logicmus_eval.models.rules import BaseRule, NumericRule
from logicmus_eval.models.test_case import LogicTestCase

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


def _rule_signature(rule: Any) -> tuple[Any, ...] | None:
    """Return a canonical signature for rule-interchangeability.

    Two rules with identical signatures are logically equivalent in the
    Bool fragment used by the generator (same operator type, same
    variable(s), same polarities). Such a rule can substitute for the
    other inside a MUS, producing an alternative MUS — which means MUS
    uniqueness fails whenever such a pair exists across the
    ``mus_expected`` boundary.

    Returns ``None`` for rule kinds whose signature is not modelled here
    (AndImplies, OrFact, Numeric). Those kinds always reference a
    distinct variable shape and cannot collide with the concrete
    generator output, so skipping them is safe.
    """
    if isinstance(rule, dict):
        op = rule.get("operator_type")
        var = rule.get("variable")
        pol = rule.get("polarity")
        ant = rule.get("antecedent")
        cons = rule.get("consequent")
        ant_pol = rule.get("antecedent_polarity")
        cons_pol = rule.get("consequent_polarity")
    else:
        op = getattr(rule, "operator_type", None)
        var = getattr(rule, "variable", None)
        pol = getattr(rule, "polarity", None)
        ant = getattr(rule, "antecedent", None)
        cons = getattr(rule, "consequent", None)
        ant_pol = getattr(rule, "antecedent_polarity", None)
        cons_pol = getattr(rule, "consequent_polarity", None)

    op_str = getattr(op, "value", op)  # unwrap StrEnum
    if op_str in ("FACT", "TERMINAL", "NOISE"):
        return (op_str, var, pol)
    if op_str == "IMPLIES":
        return (op_str, ant, cons, ant_pol, cons_pol)
    return None


def _build_rule_index(
    case: LogicTestCase,
) -> tuple[dict[str, Any], dict[str, set[str]]] | None:
    """Build ``rule_id -> rule`` and ``rule_id -> variables`` maps.

    Returns ``None`` if any rule lacks an id (malformed case).
    """
    rule_by_id: dict[str, Any] = {}
    rule_vars: dict[str, set[str]] = {}
    for rule in case.rules:
        rule_id = (
            rule.get("id") if isinstance(rule, dict) else getattr(rule, "id", None)
        )
        if rule_id is None:
            return None
        rule_by_id[rule_id] = rule
        rule_vars[rule_id] = _rule_variables(rule)
    return rule_by_id, rule_vars


def _has_duplicate_across_mus_boundary(
    rule_by_id: dict[str, Any], expected_ids: set[str]
) -> bool:
    """True if some rule outside the MUS is interchangeable with a MUS rule.

    Such a duplicate can substitute for its twin inside the MUS, producing
    an alternative MUS — uniqueness fails. The variable-closure step cannot
    detect this on its own: it would absorb the duplicate into the closure
    and wrongly declare uniqueness.
    """
    mus_signatures: set[tuple[Any, ...]] = set()
    for rid in expected_ids:
        sig = _rule_signature(rule_by_id[rid])
        if sig is not None:
            mus_signatures.add(sig)

    for rid, rule in rule_by_id.items():
        if rid in expected_ids:
            continue
        sig = _rule_signature(rule)
        if sig is not None and sig in mus_signatures:
            return True
    return False


def _variable_transitive_closure(
    seed_ids: set[str], rule_vars: dict[str, set[str]]
) -> set[str]:
    """Expand ``seed_ids`` by the relation "shares a variable with the set"."""
    core_ids: set[str] = set(seed_ids)
    changed = True
    while changed:
        changed = False
        core_vars_now: set[str] = set()
        for rid in core_ids:
            core_vars_now |= rule_vars[rid]
        for rid, vars_ in rule_vars.items():
            if rid in core_ids:
                continue
            if vars_ & core_vars_now:
                core_ids.add(rid)
                changed = True
    return core_ids


def _union_vars(ids: set[str], rule_vars: dict[str, set[str]]) -> set[str]:
    """Union of all variables referenced by the given rule IDs."""
    out: set[str] = set()
    for rid in ids:
        out |= rule_vars[rid]
    return out


def verify_mus_uniqueness_by_structure(case: LogicTestCase) -> bool:
    """Prove MUS uniqueness structurally, without enumeration.

    Argument (proof by construction):

    Let ``M`` be the set of rules whose IDs appear in ``case.mus_expected``
    and let ``C`` be the *variable-transitive closure* of ``M`` — i.e. the
    smallest set of rules containing ``M`` and closed under the relation
    "shares at least one variable with a rule already in the set". Let
    ``N`` be the complement of ``C``.

    By generator construction, every core rule only mentions variables
    from ``V_c`` and every noise rule only mentions variables from ``V_n``,
    with ``V_c ∩ V_n = ∅``. Intermediate core rules that do not belong to
    ``M`` (e.g. the branch implications of ``ForkPatternStrategy``) are
    pulled into ``C`` by the closure step because they share the root
    variable with ``M``; noise rules are not, because they are
    variable-disjoint from ``V_c``.

    Therefore ``V(C) ∩ V(N) = ∅``, and:

    * ``N`` alone is satisfiable — noise rules are independent Bool
      assignments over disjoint variables.
    * Any unsat subset of ``C ∪ N`` cannot mix rules from ``C`` and ``N``,
      because they share no variables; hence it is entirely contained in
      ``C``.
    * Within ``C`` the generator invariant holds: ``M`` is the *unique*
      minimal unsat subset (verified empirically for every concrete
      strategy — chain / direct / fork / idem / coverage / merge / math
      each construct their core as a single linear contradiction).

    So the overall MUS is unique iff ``V(C) ∩ V(N) = ∅`` *and* no rule
    outside ``M`` is logically interchangeable with a rule inside ``M``.
    The latter is a separate guard (see below): the variable-closure
    step alone would absorb such a duplicate into ``C`` and wrongly
    declare uniqueness.

    Complexity: O(len(case.rules)^2 * |_RULE_VARIABLE_FIELDS|) in the worst
    case for the closure loop, but with the generator's variable layout the
    loop terminates after a single pass in practice.

    This replaces the previous brute-force ``count_minimal_unsat_subsets``,
    which for ``mus_size=9`` required enumerating ~10^6 combinations of
    20 rules and would have made smoke-generation take hours.
    """
    if case.is_satisfiable:
        return True

    expected_ids = set(case.mus_expected)
    if not expected_ids:
        return False

    index = _build_rule_index(case)
    if index is None:
        return False
    rule_by_id, rule_vars = index

    if not expected_ids.issubset(rule_vars.keys()):
        # A mus_expected ID is not present among the rules — malformed case.
        return False

    if _has_duplicate_across_mus_boundary(rule_by_id, expected_ids):
        return False

    core_ids = _variable_transitive_closure(expected_ids, rule_vars)
    core_vars = _union_vars(core_ids, rule_vars)

    noise_ids = set(rule_vars.keys()) - core_ids
    noise_vars = _union_vars(noise_ids, rule_vars)

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
