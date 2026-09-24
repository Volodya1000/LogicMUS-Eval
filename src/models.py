from typing import Any

import z3
from pydantic import BaseModel, Field

from src.enums import TemplatePackId


class BaseRule(BaseModel):
    id: str
    text: str
    is_fact: bool = False
    is_noise: bool = False

    def to_z3(self) -> z3.ExprRef:
        raise NotImplementedError


class FactRule(BaseRule):
    variable: str
    predicate: str
    polarity: bool
    is_fact: bool = True

    def to_z3(self) -> z3.ExprRef:
        var_expr = z3.Bool(self.variable)
        return var_expr if self.polarity else z3.Not(var_expr)


class ImpliesRule(BaseRule):
    antecedent: str
    consequent: str
    antecedent_predicate: str
    consequent_predicate: str
    antecedent_polarity: bool
    consequent_polarity: bool

    def to_z3(self) -> z3.ExprRef:
        ant_expr = z3.Bool(self.antecedent)
        if not self.antecedent_polarity:
            ant_expr = z3.Not(ant_expr)
        cons_expr = z3.Bool(self.consequent)
        if not self.consequent_polarity:
            cons_expr = z3.Not(cons_expr)
        return z3.Implies(ant_expr, cons_expr)


class TerminalRule(BaseRule):
    variable: str
    predicate: str
    polarity: bool

    def to_z3(self) -> z3.ExprRef:
        var_expr = z3.Bool(self.variable)
        return var_expr if self.polarity else z3.Not(var_expr)


class NoiseRule(BaseRule):
    variable: str
    predicate: str
    polarity: bool
    is_noise: bool = True

    def to_z3(self) -> z3.ExprRef:
        var_expr = z3.Bool(self.variable)
        return var_expr if self.polarity else z3.Not(var_expr)


Rule = FactRule | ImpliesRule | TerminalRule | NoiseRule


class LogicTestCase(BaseModel):
    case_id: str
    k: int
    is_satisfiable: bool
    template_pack_id: TemplatePackId
    predicate_mapping: dict[str, str]
    rules: list[Rule]
    mus_expected: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class ArtifactsManifest(BaseModel):
    dataset_filename: str
    dataset_sha256: str
    source_bundle_sha256: str


class EnvironmentManifest(BaseModel):
    python: str
    z3: str
    numpy: str
    scikit_learn: str


class ParametersManifest(BaseModel):
    k_values: list[int]
    pairs_per_group: int
    total_cases: int
    rules_per_case: int
    base_seed: int


class TfidfMetrics(BaseModel):
    mean_f1: float
    std_f1: float


class LeakageMetricsGlobal(BaseModel):
    word_tfidf: TfidfMetrics
    char_tfidf: TfidfMetrics


class BenchmarkManifest(BaseModel):
    artifacts: ArtifactsManifest
    environment: EnvironmentManifest
    parameters: ParametersManifest
    validation_results: dict[str, str]
    leakage_metrics_global: LeakageMetricsGlobal
    leakage_metrics_by_k: dict[str, dict[str, TfidfMetrics]]
