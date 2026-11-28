"""Offline evidence verification for the explicitly bounded development mode."""

import json
from pathlib import Path
from typing import Annotated

import typer

from logicmus_eval.confirmation.infrastructure_evidence import check_development_smoke
from logicmus_eval.confirmation.models import SmokeEvidence
from logicmus_eval.runner.config import load_config


def check_smoke_evidence(
    root: Annotated[Path, typer.Option("--root")],
    config: Annotated[Path, typer.Option("--config")],
    evidence: Annotated[Path, typer.Option("--evidence")],
) -> None:
    """OFFLINE: verify real evidence; never send requests or admit research data."""
    try:
        document = SmokeEvidence.model_validate_json(
            evidence.read_text(encoding="utf-8")
        )
        check_development_smoke(root.resolve(), load_config(config), document)
    except (ValueError, OSError, KeyError) as error:
        typer.echo(json.dumps({"real_smoke": "not_verified", "issue": str(error)}))
        raise typer.Exit(1) from error
    typer.echo(
        json.dumps(
            {
                "real_smoke": "passed",
                "scope": "infrastructure-smoke-v1",
                "standalone_research_admission": "not_admitted",
            }
        )
    )
