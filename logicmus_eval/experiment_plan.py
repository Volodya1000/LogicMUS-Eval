"""Strict, canonical plans for controlled experiments, separate from legacy v2."""

import hashlib
import json
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from logicmus_eval.run_pipeline import STRATEGY_REGISTRY
from logicmus_eval.templates import PREDICATE_POOL

PROTOCOL_VERSION = "controlled-v1"
ControlledProtocol = Literal["controlled-v1", "controlled-v2"]
PATTERNS = {strategy.name: strategy for strategy in STRATEGY_REGISTRY}
SCALABLE_PATTERNS = frozenset({"chain", "math"})


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_id(*parts: object) -> str:
    return hashlib.sha256(canonical_json(parts).encode("utf-8")).hexdigest()


class PlanModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PatternSelection(PlanModel):
    pattern_id: str
    k_values: list[int] = Field(min_length=1)


class ExperimentSeries(PlanModel):
    series_id: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    kind: Literal["noise_sweep", "k_sweep", "topology_panel"]
    patterns: list[PatternSelection] = Field(min_length=1)
    n_values: list[int] = Field(min_length=1)
    ordering: Literal["stable_insertion"] = "stable_insertion"

    @model_validator(mode="after")
    # The validator mirrors the three explicit series contracts.
    # pylint: disable=too-many-branches
    def check_series(self) -> Self:
        if len(set(self.n_values)) != len(self.n_values):
            raise ValueError("Duplicate N values")
        names = [p.pattern_id for p in self.patterns]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate patterns in a series")
        if self.kind == "noise_sweep" and (
            len(self.patterns) != 1 or len(self.patterns[0].k_values) != 1
        ):
            raise ValueError("noise_sweep requires one pattern and one K")
        if self.kind == "topology_panel" and len(self.n_values) != 1:
            raise ValueError(
                "topology_panel requires one N; use separate panels for other N"
            )
        if self.kind == "k_sweep":
            if len(self.n_values) != 1:
                raise ValueError("k_sweep requires one N")
            if len(names) != 1 or names[0] not in SCALABLE_PATTERNS:
                raise ValueError("k_sweep requires one scalable family: chain or math")
        for selection in self.patterns:
            if selection.pattern_id not in PATTERNS:
                raise ValueError(f"Unknown pattern: {selection.pattern_id}")
            if len(set(selection.k_values)) != len(selection.k_values):
                raise ValueError("Duplicate K values")
            strategy = PATTERNS[selection.pattern_id]
            for k in selection.k_values:
                if not strategy.supports(k):
                    raise ValueError(f"{selection.pattern_id} does not support K={k}")
                construction = strategy.core_rule_count(k)
                for n in self.n_values:
                    if n < construction:
                        raise ValueError(
                            f"{selection.pattern_id} K={k}: N={n} < construction={construction}"
                        )
                    needed = strategy.core_variable_count(k) + n - construction
                    if needed > len(PREDICATE_POOL):
                        raise ValueError(
                            f"{selection.pattern_id} K={k} N={n}: predicate pool "
                            f"needs {needed}, available {len(PREDICATE_POOL)}"
                        )
        return self


class ExperimentCell(PlanModel):
    cell_id: str
    series_id: str
    series_kind: Literal["noise_sweep", "k_sweep", "topology_panel"]
    pattern_id: str
    k: int
    n: int


def family_identity(
    pattern_id: str,
    k: int,
    seed: int,
    index: int,
    protocol_version: ControlledProtocol = "controlled-v1",
) -> str:
    return content_id(protocol_version, pattern_id, k, seed, index)


def case_identity(
    cell: ExperimentCell,
    seed: int,
    index: int,
    is_sat: bool,
    protocol_version: ControlledProtocol = "controlled-v1",
) -> str:
    return content_id(
        cell.cell_id,
        family_identity(cell.pattern_id, cell.k, seed, index, protocol_version),
        is_sat,
    )


class ExperimentPlan(PlanModel):
    protocol_version: ControlledProtocol
    purpose: Literal["development", "confirmation"]
    seeds: list[int] = Field(min_length=1)
    pairs_per_seed: int = Field(ge=1)
    series: list[ExperimentSeries] = Field(min_length=1)
    split_rule: Literal["even_development_odd_confirmation"] = (
        "even_development_odd_confirmation"
    )
    leakage_threshold: float = Field(default=0.55, ge=0.5, le=0.55)

    @model_validator(mode="after")
    def check_plan(self) -> Self:
        if len(set(self.seeds)) != len(self.seeds) or any(s < 0 for s in self.seeds):
            raise ValueError("Seeds must be unique nonnegative integers")
        parity = 0 if self.purpose == "development" else 1
        if any(seed % 2 != parity for seed in self.seeds):
            requirement = "even seeds" if parity == 0 else "odd seeds"
            raise ValueError(f"{self.purpose} requires {requirement} under split_rule")
        names = [s.series_id for s in self.series]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate series_id")
        return self

    def normalized(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["seeds"] = sorted(self.seeds)
        payload["series"] = sorted(payload["series"], key=lambda s: s["series_id"])
        for series in payload["series"]:
            series["n_values"].sort()
            series["patterns"].sort(key=lambda p: p["pattern_id"])
            for pattern in series["patterns"]:
                pattern["k_values"].sort()
        return payload

    @property
    def plan_hash(self) -> str:
        return hashlib.sha256(canonical_json(self.normalized()).encode()).hexdigest()

    def cells(self) -> list[ExperimentCell]:
        return [
            ExperimentCell(
                cell_id=content_id(
                    self.protocol_version,
                    self.purpose,
                    series["series_id"],
                    series["kind"],
                    selection["pattern_id"],
                    k,
                    n,
                ),
                series_id=series["series_id"],
                series_kind=series["kind"],
                pattern_id=selection["pattern_id"],
                k=k,
                n=n,
            )
            for series in self.normalized()["series"]
            for selection in series["patterns"]
            for k in selection["k_values"]
            for n in series["n_values"]
        ]
