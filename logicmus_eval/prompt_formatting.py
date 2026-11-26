"""Pure formatting shared by model inputs and offline leakage probes."""

from typing import Any

from logicmus_eval.models.test_case import LogicTestCase


def _extract_variable_expr(rule_dict: dict[str, Any]) -> str | None:
    """Derive a compact variable expression from a rule dict.

    Returns None when no recognisable variable field is present, in
    which case the caller omits the ``Var:`` section entirely. This
    keeps the helper tolerant to future rule types without touching
    the formatter.
    """
    if rule_dict.get("variable"):
        return str(rule_dict["variable"])

    antecedent = rule_dict.get("antecedent")
    consequent = rule_dict.get("consequent")
    if antecedent and consequent:
        return f"{antecedent} -> {consequent}"

    antecedent1 = rule_dict.get("antecedent1")
    antecedent2 = rule_dict.get("antecedent2")
    if antecedent1 and antecedent2 and consequent:
        return f"{antecedent1} & {antecedent2} -> {consequent}"

    variable1 = rule_dict.get("variable1")
    variable2 = rule_dict.get("variable2")
    if variable1 and variable2:
        return f"{variable1} | {variable2}"

    left_var = rule_dict.get("left_var")
    right_var = rule_dict.get("right_var")
    if left_var and right_var:
        operator = rule_dict.get("operator", "?")
        return f"{left_var} {operator} {right_var}"

    return None


def format_rules_block(case: LogicTestCase) -> str:
    """Format case rules as an ``ID | Var | Rule`` block for prompts.

    Including the ``Var:`` field makes the block self-contained: the
    model no longer has to infer the variable-to-predicate mapping from
    the free-text rule body.
    """
    lines: list[str] = []
    for rule in case.rules:
        rule_dict = rule if isinstance(rule, dict) else rule.model_dump()
        var_expr = _extract_variable_expr(rule_dict)
        if var_expr is not None:
            lines.append(
                f"ID: {rule_dict['id']} | Var: {var_expr} | Rule: {rule_dict['text']}"
            )
        else:
            lines.append(f"ID: {rule_dict['id']} | Rule: {rule_dict['text']}")
    return "\n".join(lines) + "\n" if lines else ""


def format_variable_block(case: LogicTestCase) -> str:
    """Format the list of Bool variables expected by the Z3 prompt."""
    if case.predicate_mapping:
        numeric_variables: set[str] = set()
        for rule in case.rules:
            data = rule if isinstance(rule, dict) else rule.model_dump()
            if data.get("left_var") is not None:
                numeric_variables.update((data["left_var"], data["right_var"]))
        return "\n".join(
            f"{var} = {'Real' if var in numeric_variables else 'Bool'}('{var}')  # {pred}"
            for var, pred in sorted(case.predicate_mapping.items())
        )

    # Fallback for cases loaded without predicate_mapping (should not
    # happen with the current generator; kept for robustness against
    # external datasets).
    variables: dict[str, str] = {}
    for rule in case.rules:
        rule_dict = rule if isinstance(rule, dict) else rule.model_dump()
        var = rule_dict.get("variable")
        if var is not None:
            variables.setdefault(var, rule_dict.get("predicate", ""))

    return "\n".join(
        f"{var} = Bool('{var}')  # {pred}" for var, pred in variables.items()
    )
