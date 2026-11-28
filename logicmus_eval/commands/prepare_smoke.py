"""Prepare a fixed infrastructure selection, entirely offline."""

from pathlib import Path
from typing import Annotated

import typer

from logicmus_eval.infrastructure_smoke import SelectionRule, prepare_selection


def prepare_smoke(
    parent_manifest: Annotated[Path, typer.Option("--parent-manifest")],
    rule: Annotated[Path, typer.Option("--rule")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    try:
        selected = prepare_selection(
            parent_manifest,
            SelectionRule.model_validate_json(rule.read_text(encoding="utf-8")),
            output,
        )
    except (ValueError, OSError) as error:
        typer.echo(f"Smoke preparation blocked: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(
        f"Selected {len(selected.case_uids)} infrastructure cases: {selected.selection_sha256}"
    )
    typer.echo("Standalone research admission: not_admitted; real smoke: not_verified")
