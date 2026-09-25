from pydantic import BaseModel


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
