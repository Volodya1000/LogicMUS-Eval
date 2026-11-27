"""Serializable request shape shared by the parent and worker."""

from typing import TypedDict


class WorkerRequest(TypedDict):
    code: str
    expected_rule_ids: list[str]
    deadline: float
