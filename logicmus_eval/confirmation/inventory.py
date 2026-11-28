"""Plan-only accounting, before generation or endpoint access."""

from collections import Counter
from typing import Any

from logicmus_eval.analysis.statistics import wilson
from logicmus_eval.experiment_plan import ExperimentPlan, family_identity
from logicmus_eval.runner.config import RunConfig


def families(plan: ExperimentPlan) -> set[str]:
    return {
        family_identity(cell.pattern_id, cell.k, seed, index)
        for cell in plan.cells()
        for seed in plan.seeds
        for index in range(plan.pairs_per_seed)
    }


def inventory(plan: ExperimentPlan, configs: dict[str, RunConfig]) -> dict[str, Any]:
    """Count cell jobs only: combined JSONL is a checked copy, never extra work."""
    per_cell = len(plan.seeds) * plan.pairs_per_seed
    cases = len(plan.cells()) * per_cell * 2
    requests = sum(cases * len(c.models) * len(c.strategies) for c in configs.values())
    token_cap = sum(
        cases * len(c.strategies) * m.generation.max_tokens
        for c in configs.values()
        for m in c.models
    )
    interval = wilson(per_cell // 2, per_cell)
    low, high = interval["low"], interval["high"]
    uses = Counter((c.pattern_id, c.k) for c in plan.cells())
    return {
        "cells": len(plan.cells()),
        "pairs_per_cell": per_cell,
        "independent_families": len(families(plan)),
        "family_cell_occurrences": per_cell * len(plan.cells()),
        "cases": cases,
        "requests": requests,
        "max_attempts": sum(
            cases * len(c.models) * len(c.strategies) * c.retry.max_attempts
            for c in configs.values()
        ),
        "output_token_cap": token_cap,
        "output_token_cap_all_attempts": sum(
            cases * len(c.strategies) * m.generation.max_tokens * c.retry.max_attempts
            for c in configs.values()
            for m in c.models
        ),
        "wilson_max_half_width": None
        if low is None or high is None
        else (high - low) / 2,
        "per_cell": [
            {
                **c.model_dump(),
                "independent_families": per_cell,
                "pairs": per_cell,
                "cases": per_cell * 2,
                "requests": sum(
                    per_cell * 2 * len(r.models) * len(r.strategies)
                    for r in configs.values()
                ),
            }
            for c in plan.cells()
        ],
        "reuse": [
            {
                "pattern_id": p,
                "K": k,
                "independent_families": per_cell,
                "cell_occurrences_per_family": count,
                "series": sorted(
                    {c.series_id for c in plan.cells() if (c.pattern_id, c.k) == (p, k)}
                ),
            }
            for (p, k), count in sorted(uses.items())
        ],
        "retry_scope": (
            "Configured automatic retry cycles only, default indeterminate_policy=halt. "
            "Explicit indeterminate retry starts a new cycle; repeated manual authorization "
            "has no finite total bound. Never create duplicate runs to resume."
        ),
        "time_and_price": "unknown; no measured inference or provider pricing",
    }
