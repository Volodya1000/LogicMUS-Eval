from pathlib import Path
from typing import Annotated

import typer

from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.experiment_preparation import SERIES_MANIFEST, prepare_experiment


def prepare(
    plan: Annotated[Path, typer.Option("--plan", exists=True, dir_okay=False)],
    output_dir: Annotated[Path, typer.Option("--output-dir")],
) -> None:
    """Prepare a controlled series offline, retaining every diagnostic failure."""
    try:
        config = ExperimentPlan.model_validate_json(plan.read_text(encoding="utf-8"))
        manifest = prepare_experiment(config, output_dir)
    except (ValueError, OSError) as error:
        typer.echo(f"Invalid experiment: {error}", err=True)
        raise typer.Exit(1) from error
    typer.echo(f"Manifest: {output_dir / SERIES_MANIFEST}")
    if not manifest.ready_for_evaluation:
        typer.echo(
            "Series not ready for evaluation; see all diagnostics in the manifest."
        )
        raise typer.Exit(1)
    typer.echo(
        "Series passed technical release checks; this is not confirmation of paper readiness."
    )
