"""Refusal-marker patterns for detecting when an LLM declined to reason.

Patterns are grouped by language. Russian patterns are authoritative for
current prompts (iteration 1+); English patterns are retained for
backward compatibility with historical reports produced by older runs
that used English prompts.

Downstream code should not depend on this module directly — use
``src.evaluation.diagnostics.is_refusal`` instead, so that the detection
mechanism can be replaced (e.g., by a structured ``confidence`` field)
without touching callers.
"""

# Russian patterns — authoritative for current (iteration 1+) prompts.
RU_REFUSAL_PATTERNS: tuple[str, ...] = (
    r"нет явных начальных",
    r"не содержат начальных состояний",
    r"невозможно выполнить логический вывод",
    r"не могу определить",
)

# Legacy English patterns — kept only so that older reports can still be
# re-classified. New prompts are Russian-only; do not extend this list.
LEGACY_EN_REFUSAL_PATTERNS: tuple[str, ...] = (
    r"no explicit initial",
    r"not explicitly provided",
    r"cannot perform logical deduction",
    r"no specific conditions",
)

REFUSAL_PATTERNS: tuple[str, ...] = RU_REFUSAL_PATTERNS + LEGACY_EN_REFUSAL_PATTERNS
