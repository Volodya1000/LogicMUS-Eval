"""Resolve a prospective AnalysisPlan against planned jobs, without responses."""

from dataclasses import dataclass

from logicmus_eval.analysis.plan import AnalysisPlan, Selection
from logicmus_eval.experiment_plan import ExperimentCell, ExperimentPlan
from logicmus_eval.runner.config import RunConfig
from logicmus_eval.runner.preflight import digest


@dataclass(frozen=True)
class PlannedSide:
    run: str
    model: str
    strategy: str
    cell: ExperimentCell


def _select(sides: list[PlannedSide], selector: Selection) -> list[PlannedSide]:
    return [
        s
        for s in sides
        if all(
            (
                selector.model_id is None or selector.model_id == s.model,
                selector.strategy is None or selector.strategy == s.strategy,
                selector.series_id is None or selector.series_id == s.cell.series_id,
                selector.pattern_id is None or selector.pattern_id == s.cell.pattern_id,
                selector.K is None or selector.K == s.cell.k,
                selector.N is None or selector.N == s.cell.n,
            )
        )
    ]


def _group_conditions(sides: list[PlannedSide], configs: dict[str, RunConfig]) -> None:
    """Mirror existing analysis common and strategy-scoped compatibility."""
    common: dict[str, str] = {}
    scoped: dict[tuple[str, str], str] = {}
    for side in sides:
        config = configs[side.run]
        model = next(m for m in config.models if m.model_id == side.model)
        condition = {
            "model": model.model_dump(mode="json"),
            "endpoint": config.endpoint,
            "timeout": config.request_timeout_seconds,
            "retry": config.retry.model_dump(mode="json"),
        }
        fingerprint = digest(condition)
        if side.model in common and common[side.model] != fingerprint:
            raise ValueError("Incompatible inference conditions within selected group")
        common[side.model] = fingerprint
        if side.strategy == "z3":
            condition["z3_timeout"] = config.z3_timeout_seconds
        specific = digest(condition)
        key = (side.model, side.strategy)
        if key in scoped and scoped[key] != specific:
            raise ValueError("Incompatible strategy conditions within selected group")
        scoped[key] = specific


# Each branch mirrors one part of the existing AnalysisPlan selection contract.
# pylint: disable=too-many-locals,too-many-branches
def validate_template(
    plan: ExperimentPlan, configs: dict[str, RunConfig], template: AnalysisPlan
) -> dict[str, int]:
    """Validate every cell and both complete sides using existing family identities.

    Logical run names occupy run_ids only in the template. Statistical settings,
    selectors, weights (none) and all other fields remain ordinary AnalysisPlan.
    """
    if template.purpose != plan.purpose or template.mode != "primary":
        raise ValueError("Prospective plan must be primary and match purpose")
    if any(config.infrastructure_smoke is not None for config in configs.values()):
        raise ValueError("Infrastructure smoke cannot enter a primary prospective plan")
    requested = [r for g in template.groups for r in g.run_ids]
    if set(requested) != configs.keys():
        raise ValueError("Logical run names must exactly cover configured runs")
    groups: dict[str, list[PlannedSide]] = {}
    for group in template.groups:
        if len(set(group.run_ids)) != len(group.run_ids):
            raise ValueError("Duplicate logical run in group")
        sides = [
            PlannedSide(r, m.model_id, strategy, cell)
            for r in group.run_ids
            for m in configs[r].models
            for strategy in configs[r].strategies
            for cell in plan.cells()
        ]
        for values, available in (
            (group.model_ids, {s.model for s in sides}),
            (group.strategies, {s.strategy for s in sides}),
            (group.cell_ids, {s.cell.cell_id for s in sides}),
        ):
            if values is not None and (
                len(values) != len(set(values)) or not set(values) <= available
            ):
                raise ValueError("Missing or duplicate group selector")
        sides = [
            s
            for s in sides
            if (group.model_ids is None or s.model in group.model_ids)
            and (group.strategies is None or s.strategy in group.strategies)
            and (group.cell_ids is None or s.cell.cell_id in group.cell_ids)
        ]
        keys = [(s.model, s.strategy, s.cell.cell_id) for s in sides]
        if not sides or len(keys) != len(set(keys)):
            raise ValueError("Empty or repeated observations in group")
        _group_conditions(sides, configs)
        groups[group.name] = sides
    counts = {}
    for contrast in template.contrasts:
        left = _select(groups[contrast.left.group], contrast.left)
        right = _select(groups[contrast.right.group], contrast.right)
        if len(left) != 1 or len(right) != 1:
            raise ValueError(
                f"Contrast {contrast.name}: select exactly one existing cell per side"
            )
        a, b = left[0], right[0]
        if (
            contrast.left.group,
            a.model,
            a.cell.series_id,
            a.cell.pattern_id,
            a.cell.k,
        ) != (
            contrast.right.group,
            b.model,
            b.cell.series_id,
            b.cell.pattern_id,
            b.cell.k,
        ):
            raise ValueError("Incompatible paired identities; K sweeps are not paired")
        ca, cb = configs[a.run], configs[b.run]
        ma = next(m for m in ca.models if m.model_id == a.model)
        mb = next(m for m in cb.models if m.model_id == b.model)
        if ma != mb or any(
            getattr(ca, f) != getattr(cb, f)
            for f in (
                "endpoint",
                "request_timeout_seconds",
                "retry",
                "z3_timeout_seconds",
            )
        ):
            raise ValueError("Incompatible model or inference conditions")
        if contrast.kind == "strategy":
            if a.cell != b.cell or {a.strategy, b.strategy} != {"direct", "z3"}:
                raise ValueError(
                    "Strategy contrast requires direct versus z3 at identical cell"
                )
        elif (
            a.cell.series_kind != "noise_sweep"
            or a.strategy != b.strategy
            or a.cell.n == b.cell.n
        ):
            raise ValueError(
                "Noise contrast requires different N in the same noise sweep"
            )
        pairs = len(plan.seeds) * plan.pairs_per_seed
        counts[contrast.name] = pairs * (
            1 if contrast.metric in {"mus_exact_match", "mus_f1"} else 2
        )
    return counts
