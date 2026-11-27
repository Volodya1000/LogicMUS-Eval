"""Normalize fenced model output without interpreting formulas."""

import re


def clean_markdown_code(code_str: str) -> str:
    cleaned: str = code_str.strip()
    match: re.Match[str] | None = re.search(
        r"```(?:python)?\s*(.*?)\s*```", cleaned, re.DOTALL
    )
    return match.group(1).strip() if match else cleaned
