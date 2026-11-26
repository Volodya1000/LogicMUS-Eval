from typing import Literal

from pydantic import BaseModel, Field


class ValidationResultDTO(BaseModel):
    is_sat_correct: bool
    is_mus_valid: bool
    is_mus_minimal: bool
    extracted_core_ids: list[str]


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
    mus_sizes: list[int]
    pairs_per_group: int
    total_cases: int
    rules_per_case: int
    base_seed: int
    generator_version: int = 1


class TfidfMetrics(BaseModel):
    mean_f1: float | None = None
    std_f1: float | None = None
    mean_balanced_accuracy: float | None = None
    std_balanced_accuracy: float | None = None
    fold_balanced_accuracies: list[float] = Field(default_factory=list)
    n_splits: int = 0
    status: Literal["ok", "unavailable", "legacy"] = "legacy"
    reason: str | None = None


class LeakageAcceptance(BaseModel):
    metric: str = "balanced_accuracy"
    threshold: float
    passed: bool
    failures: list[str] = Field(default_factory=list)
    cv_grouping: str = "pair_id"


class LeakageMetricsGlobal(BaseModel):
    word_tfidf: TfidfMetrics
    char_tfidf: TfidfMetrics


class ValidationResultsManifest(BaseModel):
    sat_correctness: str
    unsat_correctness: str
    mus_validity: str
    mus_minimality: str


class BenchmarkManifest(BaseModel):
    artifacts: ArtifactsManifest
    environment: EnvironmentManifest
    parameters: ParametersManifest
    validation_results: ValidationResultsManifest
    leakage_metrics_global: LeakageMetricsGlobal
    leakage_metrics_by_mus_size: dict[str, dict[str, TfidfMetrics]]
    leakage_acceptance: LeakageAcceptance | None = None
