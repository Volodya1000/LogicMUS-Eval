"""Typed analysis domain and persisted artifact contracts."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, NotRequired, TypedDict

from pydantic import Field, JsonValue

from logicmus_eval.analysis.plan import AnalysisPlan, Intervals, Metric, Selection
from logicmus_eval.models.evaluation import (
    EvaluationCaseReport,
    ExperimentProvenance,
    Purpose,
    SeriesKind,
)
from logicmus_eval.runner.config import ModelConfig, RetryConfig, StrictModel
from logicmus_eval.runner.snapshot_models import (
    RunnerProvenance,
    RuntimeVersions,
    SavedJob,
    Strategy,
    TraceIdentity,
)

if TYPE_CHECKING:
    from logicmus_eval.analysis.sources import Snapshot


class ConfidenceInterval(TypedDict):
    status: Literal["ok", "unavailable"]
    reason: str | None
    low: float | None
    high: float | None
    families: int
    degenerate: bool | None
    scope: Literal["pointwise"]
    method: NotRequired[Literal["wilson", "family-cluster-percentile"]]


@dataclass(frozen=True, order=True)
class AnalysisDimensions:  # pylint: disable=too-many-instance-attributes
    # Independent analysis axes; keep the fixed domain schema visible.
    group: str
    purpose: Purpose
    series_id: str
    series_kind: SeriesKind
    pattern_id: str
    k: int
    n: int
    model_id: str
    strategy: Strategy

    def family_key(self) -> tuple[str, str, str, str, int, str]:
        return (
            self.purpose,
            self.series_id,
            self.series_kind,
            self.pattern_id,
            self.k,
            self.model_id,
        )


@dataclass(frozen=True)
class AnalysisRow:
    dimensions: AnalysisDimensions
    provenance: ExperimentProvenance
    job: SavedJob
    run_id: str
    outcome: EvaluationCaseReport
    snapshot: "Snapshot"
    trace: TraceIdentity


@dataclass(frozen=True)
class ScoredObservation:
    row: AnalysisRow
    value: float


@dataclass(frozen=True)
class CompatibilityConditions:  # pylint: disable=too-many-instance-attributes
    # The saved compatibility contract intentionally lists every compared condition.
    runner_protocol: str
    transport_protocol: str
    report_schema_version: int
    metric_definitions_version: str
    source_bundle_sha256: str
    runtime: RuntimeVersions
    model: ModelConfig
    endpoint: str
    request_timeout_seconds: float
    retry: RetryConfig
    z3_execution_protocol_version: str | None
    z3_timeout_seconds: float | None


class CompatibilityDiagnostic(StrictModel):
    status: Literal["compatible"] = "compatible"
    common_conditions: dict[str, str] = Field(default_factory=dict)
    strategy_conditions: dict[str, str] = Field(default_factory=dict)
    schema_parameter_hashes: dict[str, str] = Field(default_factory=dict)
    unknowns: list[str] = Field(
        default_factory=lambda: [
            "Unobserved model facts and backend-applied settings remain unverified."
        ]
    )


class ContrastDiagnostic(StrictModel):
    name: str
    missing_left: list[str]
    missing_right: list[str]


class RunDiagnostic(StrictModel):
    run_id: str
    planned: int
    processed: int
    provenance: RunnerProvenance
    missing_job_ids: list[str]


class AnalysisDiagnostics(StrictModel):
    mode: Literal["primary", "diagnostic", "legacy"]
    runs: list[RunDiagnostic] = Field(default_factory=list)
    compatibility: dict[str, CompatibilityDiagnostic] = Field(default_factory=dict)
    contrasts: list[ContrastDiagnostic] = Field(default_factory=list)
    error: str | None = None
    notice: str | None = None


class ReportEvidence(StrictModel):
    path: str
    sha256: str


class RunEvidence(StrictModel):
    run_id: str
    root: str
    manifest_sha256: str
    identity_sha256: str
    journal_head_sha256: str
    journal_event_count: int
    files: dict[str, str]
    supplied_reports: list[ReportEvidence]


class LegacyEvidence(ReportEvidence):
    pass


class AnalysisManifest(StrictModel):
    analysis_version: Literal["controlled-analysis-v1"]
    plan: AnalysisPlan
    plan_sha256: str
    methods: Intervals
    scope: Literal["pointwise"] = "pointwise"
    analyzer_source_bundle_sha256: str
    inputs: list[RunEvidence | LegacyEvidence] = Field(default_factory=list)
    status: Literal["running", "complete", "rejected"] = "running"
    artifacts: dict[str, str] = Field(default_factory=dict)
    plots_requested: bool = False


@dataclass(frozen=True)
class SummaryResult:  # pylint: disable=too-many-instance-attributes
    dimensions: AnalysisDimensions
    metrics: dict[str, "JsonValue"]
    families: int
    unsat_families: int
    run_ids: list[str]
    error_bucket_counts: dict[str, int]
    error_bucket_fractions: dict[str, float]
    intervals: dict[Metric, ConfidenceInterval]


@dataclass(frozen=True)
class ContrastResult:  # pylint: disable=too-many-instance-attributes
    name: str
    kind: Literal["strategy", "noise"]
    metric: Metric
    left: Selection
    right: Selection
    pairs: int
    estimate: float
    interval: ConfidenceInterval
    direction: Literal["right-minus-left"] = "right-minus-left"
