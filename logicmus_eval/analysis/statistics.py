"""Pointwise intervals; whole-family resampling, stable under input permutation."""

from collections import defaultdict
from random import Random
from statistics import NormalDist

from logicmus_eval.analysis.models import ConfidenceInterval


def unavailable(reason: str, families: int) -> ConfidenceInterval:
    return {
        "status": "unavailable",
        "reason": reason,
        "low": None,
        "high": None,
        "families": families,
        "degenerate": None,
        "scope": "pointwise",
    }


def wilson(
    successes: int, count: int, level: float = 0.95, min_families: int = 2
) -> ConfidenceInterval:
    if not 0 <= successes <= count:
        raise ValueError("Invalid binomial counts")
    if count < min_families:
        return unavailable("insufficient independent families", count)
    z = NormalDist().inv_cdf((1 + level) / 2)
    p = successes / count
    denominator = 1 + z * z / count
    center = (p + z * z / (2 * count)) / denominator
    radius = z * (p * (1 - p) / count + z * z / (4 * count**2)) ** 0.5 / denominator
    return {
        "status": "ok",
        "reason": None,
        "low": max(0, center - radius),
        "high": min(1, center + radius),
        "families": count,
        "degenerate": False,
        "scope": "pointwise",
        "method": "wilson",
    }


def _percentile(values: list[float], probability: float) -> float:
    index = (len(values) - 1) * probability
    left = int(index)
    fraction = index - left
    return (
        values[left] * (1 - fraction)
        + values[min(left + 1, len(values) - 1)] * fraction
    )


def cluster_interval(
    rows: list[tuple[str, float]],
    *,
    seed: int,
    repeats: int = 10_000,
    level: float = 0.95,
    min_families: int = 2,
) -> ConfidenceInterval:
    """Row-weighted mean; a sampled family contributes every related row together.

    For paired contrasts rows contain within-pair differences. The same family
    multiplicity therefore applies to both sides, including unequal cluster sizes.
    """
    clusters: dict[str, list[float]] = defaultdict(list)
    for family, value in sorted(rows):
        clusters[family].append(value)
    if len(clusters) < min_families:
        return unavailable("insufficient independent families", len(clusters))
    totals = [(sum(values), len(values)) for _, values in sorted(clusters.items())]
    rng = Random(seed)
    distribution = []
    for _ in range(repeats):
        sample = rng.choices(totals, k=len(totals))
        distribution.append(
            sum(total for total, _ in sample) / sum(count for _, count in sample)
        )
    distribution.sort()
    alpha = (1 - level) / 2
    degenerate = distribution[0] == distribution[-1]
    return {
        "status": "ok",
        "reason": "degenerate bootstrap; no equivalence or population-perfection claim"
        if degenerate
        else None,
        "low": _percentile(distribution, alpha),
        "high": _percentile(distribution, 1 - alpha),
        "families": len(clusters),
        "degenerate": degenerate,
        "scope": "pointwise",
        "method": "family-cluster-percentile",
    }
