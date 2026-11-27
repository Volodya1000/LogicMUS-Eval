"""Metrics over finalized case outcomes; no metric reinterprets eligibility."""

from pydantic import JsonValue

from logicmus_eval.evaluation.metrics.accounting import _ratio
from logicmus_eval.evaluation.metrics.base import BaseMetric


class TokenUsageMetric(BaseMetric):
    def compute(self) -> dict[str, JsonValue]:
        values: dict[str, list[int | None]] = {
            "prompt_tokens": [r.metadata.prompt_tokens for r in self.reports],
            "completion_tokens": [r.metadata.completion_tokens for r in self.reports],
            "thinking_tokens": [r.metadata.thinking_tokens for r in self.reports],
            "total_tokens": [r.metadata.total_tokens for r in self.reports],
        }
        known: dict[str, list[int]] = {
            name: [v for v in counts if v is not None]
            for name, counts in values.items()
        }
        return {
            "total_tokens_consumed": sum(known["total_tokens"])
            if known["total_tokens"]
            else None,
            "total_thinking_tokens": sum(known["thinking_tokens"])
            if known["thinking_tokens"]
            else None,
            **{
                f"avg_{name}": _ratio(sum(known[name]), len(known[name]))
                for name in ("prompt_tokens", "completion_tokens", "thinking_tokens")
            },
            "usage_known_cases": {k: len(v) for k, v in known.items()},
            "usage_coverage": {
                k: _ratio(len(v), len(self.reports)) for k, v in known.items()
            },
            # Failed attempts have unobserved costs even when a retry succeeds.
            "token_accounting_complete": bool(self.reports)
            and all(
                r.metadata.total_tokens is not None and r.metadata.request_attempts == 1
                for r in self.reports
            ),
        }
