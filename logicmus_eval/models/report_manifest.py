"""Thin report manifest DTOs shared by runners and analysis."""

from pathlib import Path

from pydantic import BaseModel


class ReportConfig(BaseModel):
    name: str
    exp: str
    mus_size: int
    total_rules: int
    pairs: int | None = None


class ReportManifestEntry(BaseModel):
    report: Path
    config: ReportConfig
    model: str
    model_label: str | None = None
    strategy: str
    planned: int | None = None
