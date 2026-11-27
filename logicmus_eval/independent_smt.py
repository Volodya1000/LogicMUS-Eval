"""Independent serialized-rule -> SMT-LIB control, without rule.to_z3().

This checks pipeline correctness with the same SMT engine, not LLM quality or
agreement between independent solvers. The encoder does not consume gold labels.
"""

import re
from typing import Any

import z3  # type: ignore[import-untyped]


def _symbol(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"p[0-9]+", value):
        raise ValueError(f"Invalid controlled variable: {value!r}")
    return value


def _literal(data: dict[str, Any], var: str, polarity: str) -> str:
    symbol = _symbol(data[var])
    return symbol if data[polarity] else f"(not {symbol})"


def serialized_formula(data: dict[str, Any]) -> str:
    """Encode every supported rule independently of production rule methods."""
    kind = data["operator_type"]
    if kind in ("FACT", "TERMINAL", "NOISE"):
        return _literal(data, "variable", "polarity")
    if kind == "IMPLIES":
        ant = _literal(data, "antecedent", "antecedent_polarity")
        cons = _literal(data, "consequent", "consequent_polarity")
        return f"(=> {ant} {cons})"
    if kind == "AND_IMPLIES":
        a = _literal(data, "antecedent1", "antecedent1_polarity")
        b = _literal(data, "antecedent2", "antecedent2_polarity")
        cons = _literal(data, "consequent", "consequent_polarity")
        return f"(=> (and {a} {b}) {cons})"
    if kind == "OR_FACT":
        a = _literal(data, "variable1", "polarity1")
        b = _literal(data, "variable2", "polarity2")
        return f"(or {a} {b})"
    if kind in ("NUMERIC_GT", "NUMERIC_LT", "NUMERIC_EQ"):
        operator = {"NUMERIC_GT": ">", "NUMERIC_LT": "<", "NUMERIC_EQ": "="}[kind]
        return f"({operator} {_symbol(data['left_var'])} {_symbol(data['right_var'])})"
    raise ValueError(f"Unsupported rule type: {kind}")


def smt_script(rules: list[dict[str, Any]]) -> str:
    variables: dict[str, str] = {}
    for rule in rules:
        numeric = rule["operator_type"] in ("NUMERIC_GT", "NUMERIC_LT", "NUMERIC_EQ")
        for field in (
            "antecedent",
            "antecedent1",
            "antecedent2",
            "consequent",
            "left_var",
            "right_var",
            "variable",
            "variable1",
            "variable2",
        ):
            if field in rule:
                name, sort = _symbol(rule[field]), "Real" if numeric else "Bool"
                if name in variables and variables[name] != sort:
                    raise ValueError(f"Conflicting variable sorts: {name}")
                variables[name] = sort
    declarations = [
        f"(declare-fun {v} () {sort})" for v, sort in sorted(variables.items())
    ]
    assertions = [f"(assert {serialized_formula(r)})" for r in rules]
    return "\n".join(declarations + assertions) + "\n"


def reference_status(rules: list[dict[str, Any]]) -> str:
    solver = z3.Solver()
    solver.add(z3.parse_smt2_string(smt_script(rules)))
    return str(solver.check())


def reference_check(case: dict[str, Any]) -> dict[str, Any]:
    rules = case["rules"]
    expected = set(case["mus_expected"])
    status = reference_status(rules)
    passed = status == ("sat" if case["is_satisfiable"] else "unsat")
    if case["is_satisfiable"]:
        passed = passed and not expected
    else:
        core = [r for r in rules if r["id"] in expected]
        passed = (
            passed and len(expected) == case["mus_size"] and len(core) == len(expected)
        )
        passed = passed and reference_status(core) == "unsat"
        # Removing any expected member from the WHOLE instance proves uniqueness
        # as well as minimality of the already UNSAT expected subset.
        passed = passed and all(
            reference_status([r for r in rules if r["id"] != rid]) == "sat"
            for rid in sorted(expected)
        )
    return {"case_id": case["case_id"], "status": status, "passed": passed}
