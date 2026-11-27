"""Strict, prospective analysis contract. Model labels never select observations."""

from typing import Literal, Self

from pydantic import Field, model_validator

from logicmus_eval.runner.config import StrictModel

Metric = Literal["mus_exact_match", "mus_f1", "sat_accuracy", "coverage"]


def default_metrics() -> list[Metric]:
    return ["sat_accuracy", "mus_f1", "coverage"]


class Intervals(StrictModel):
    method: Literal["wilson-and-cluster-percentile"] = "wilson-and-cluster-percentile"
    level: float = Field(default=0.95, gt=0, lt=1)
    repeats: int = Field(default=10_000, ge=2)
    seed: int
    min_families: int = Field(default=2, ge=2)


class Group(StrictModel):
    name: str = Field(min_length=1)
    run_ids: list[str] = Field(min_length=1)
    model_ids: list[str] | None = Field(default=None, min_length=1)
    strategies: list[Literal["direct", "z3"]] | None = Field(default=None, min_length=1)
    cell_ids: list[str] | None = Field(default=None, min_length=1)


class Selection(StrictModel):
    group: str
    model_id: str | None = None
    strategy: Literal["direct", "z3"] | None = None
    series_id: str | None = None
    pattern_id: str | None = None
    K: int | None = Field(default=None, gt=0)
    N: int | None = Field(default=None, gt=0)


class Contrast(StrictModel):
    name: str = Field(min_length=1)
    kind: Literal["strategy", "noise"]
    metric: Metric = "mus_exact_match"
    left: Selection
    right: Selection


class AnalysisPlan(StrictModel):
    analysis_version: Literal["controlled-analysis-v1"]
    purpose: Literal["development", "confirmation"]
    mode: Literal["primary", "diagnostic", "legacy"] = "primary"
    groups: list[Group] = Field(min_length=1)
    primary_metric: Literal["mus_exact_match"] = "mus_exact_match"
    additional_metrics: list[Metric] = Field(default_factory=default_metrics)
    contrasts: list[Contrast] = Field(default_factory=list)
    intervals: Intervals

    @model_validator(mode="after")
    def check_names(self) -> Self:
        names = [group.name for group in self.groups]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate group name")
        contrast_names = [item.name for item in self.contrasts]
        if len(contrast_names) != len(set(contrast_names)):
            raise ValueError("Duplicate contrast name")
        for item in self.contrasts:
            if item.left.group not in names or item.right.group not in names:
                raise ValueError("Contrast selects unknown group")
        return self
