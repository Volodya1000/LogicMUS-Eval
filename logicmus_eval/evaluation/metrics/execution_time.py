"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from pydantic import JsonValue

from logicmus_eval.evaluation.metrics.accounting import _ratio
from logicmus_eval.evaluation.metrics.base import BaseMetric


class ExecutionTimeMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        known: list[float] = [
            r.metadata.case_latency_seconds
            for r in self.reports
            if r.metadata.case_latency_seconds is not None
        ]
        llm: list[float] = [
            r.metadata.llm_latency_seconds
            for r in self.reports
            if r.metadata.llm_latency_seconds is not None
        ]
        return {
            "total_execution_seconds": sum(known) if known else None,
            "avg_latency_seconds": _ratio(sum(known), len(known)),
            "latency_known_cases": len(known),
            "latency_coverage": _ratio(len(known), len(self.reports)),
            "total_llm_seconds": sum(llm) if llm else None,
            "avg_llm_latency_seconds": _ratio(sum(llm), len(llm)),
            "llm_latency_known_cases": len(llm),
            "llm_latency_coverage": _ratio(len(llm), len(self.reports)),
        }
