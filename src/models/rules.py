from typing import Literal

import z3  # type: ignore
from pydantic import BaseModel

from src.enums import OperatorType


class BaseRule(BaseModel):
    id: str
    text: str
    operator_type: OperatorType

    @property
    def is_fact(self) -> bool:
        return self.operator_type in (OperatorType.FACT, OperatorType.OR_FACT)

    @property
    def is_noise(self) -> bool:
        return self.operator_type == OperatorType.NOISE

    def to_z3(self) -> z3.ExprRef:
        raise NotImplementedError()


class FactRule(BaseRule):
    variable: str
    predicate: str
    polarity: bool
    operator_type: Literal[OperatorType.FACT] = OperatorType.FACT

    def to_z3(self) -> z3.ExprRef:
        expr = z3.Bool(self.variable)
        return expr if self.polarity else z3.Not(expr)


class ImpliesRule(BaseRule):
    antecedent: str
    consequent: str
    antecedent_predicate: str
    consequent_predicate: str
    antecedent_polarity: bool
    consequent_polarity: bool
    operator_type: Literal[OperatorType.IMPLIES] = OperatorType.IMPLIES

    def to_z3(self) -> z3.ExprRef:
        ant = z3.Bool(self.antecedent)
        cons = z3.Bool(self.consequent)
        ant_expr = ant if self.antecedent_polarity else z3.Not(ant)
        cons_expr = cons if self.consequent_polarity else z3.Not(cons)
        return z3.Implies(ant_expr, cons_expr)


class TerminalRule(BaseRule):
    variable: str
    predicate: str
    polarity: bool
    operator_type: Literal[OperatorType.TERMINAL] = OperatorType.TERMINAL

    def to_z3(self) -> z3.ExprRef:
        expr = z3.Bool(self.variable)
        return expr if self.polarity else z3.Not(expr)


class NoiseRule(BaseRule):
    variable: str
    predicate: str
    polarity: bool
    operator_type: Literal[OperatorType.NOISE] = OperatorType.NOISE

    def to_z3(self) -> z3.ExprRef:
        expr = z3.Bool(self.variable)
        return expr if self.polarity else z3.Not(expr)


class AndImpliesRule(BaseRule):
    antecedent1: str
    antecedent2: str
    consequent: str
    antecedent1_predicate: str
    antecedent2_predicate: str
    consequent_predicate: str
    operator_type: Literal[OperatorType.AND_IMPLIES] = OperatorType.AND_IMPLIES

    def to_z3(self) -> z3.ExprRef:
        ant1 = z3.Bool(self.antecedent1)
        ant2 = z3.Bool(self.antecedent2)
        cons = z3.Bool(self.consequent)
        return z3.Implies(z3.And(ant1, ant2), cons)


class OrFactRule(BaseRule):
    variable1: str
    variable2: str
    predicate1: str
    predicate2: str
    operator_type: Literal[OperatorType.OR_FACT] = OperatorType.OR_FACT

    def to_z3(self) -> z3.ExprRef:
        var1 = z3.Bool(self.variable1)
        var2 = z3.Bool(self.variable2)
        return z3.Or(var1, var2)
