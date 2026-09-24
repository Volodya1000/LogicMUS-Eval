import z3

from src.models import (
    LogicTestCase,
    Rule,
)


class LogicVerifier:
    @staticmethod
    def _rule_to_z3_expr(r: Rule) -> z3.ExprRef:
        return r.to_z3()

    @staticmethod
    def _build_z3_constraints(
        case: LogicTestCase,
    ) -> tuple[z3.Solver, dict[str, z3.BoolRef]]:
        solver = z3.Solver()
        rule_literals: dict[str, z3.BoolRef] = {}
        for r in case.rules:
            lit = z3.Bool(f"track_{r.id}")
            expr = LogicVerifier._rule_to_z3_expr(r)
            solver.assert_and_track(expr, lit)
            rule_literals[r.id] = lit
        return solver, rule_literals

    @staticmethod
    def extract_unsat_core(case: LogicTestCase) -> list[str]:
        solver, rule_literals = LogicVerifier._build_z3_constraints(case)
        if solver.check() == z3.unsat:
            core = solver.unsat_core()
            lit_to_id = {v.decl().name(): k for k, v in rule_literals.items()}
            return sorted([lit_to_id[c.decl().name()] for c in core])
        return []

    @staticmethod
    def check_minimality(case: LogicTestCase, core_ids: list[str]) -> bool:
        rules_by_id = {r.id: r for r in case.rules}
        for rid in core_ids:
            sub_solver = z3.Solver()
            for other_id in core_ids:
                if other_id == rid:
                    continue
                r = rules_by_id[other_id]
                sub_solver.add(LogicVerifier._rule_to_z3_expr(r))
            if sub_solver.check() != z3.sat:
                return False
        return True

    @staticmethod
    def verify_case(
        case: LogicTestCase,
    ) -> tuple[bool, bool, bool, list[str]]:
        solver, _ = LogicVerifier._build_z3_constraints(case)
        status = solver.check()

        if case.is_satisfiable:
            is_sat_correct = status == z3.sat
            return is_sat_correct, False, False, []
        else:
            is_sat_correct = status == z3.unsat
            if not is_sat_correct:
                return False, False, False, []

            core = LogicVerifier.extract_unsat_core(case)
            expected_set = set(case.mus_expected)
            actual_set = set(core)

            mus_valid = expected_set == actual_set
            mus_minimal = LogicVerifier.check_minimality(case, core)

            return is_sat_correct, mus_valid, mus_minimal, core
