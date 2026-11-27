"""Offline analysis command; intentionally no inference/transport imports."""

from pathlib import Path
from typing import Annotated

import typer

from logicmus_eval.analysis import analyze
from logicmus_eval.analysis.plan import AnalysisPlan


def controlled(
    run: Annotated[
        list[Path],
        typer.Option(
            "--run", help="Saved run directory, report, or parent directory; repeatable"
        ),
    ],
    plan: Annotated[Path, typer.Option("--plan", exists=True, dir_okay=False)],
    output: Annotated[
        Path, typer.Option("--output", help="Fresh separate artifact directory")
    ],
    plots: Annotated[bool, typer.Option("--plots/--no-plots")] = True,
) -> None:
    try:
        parsed = AnalysisPlan.model_validate_json(plan.read_text(encoding="utf-8"))
        analyze(run, parsed, output, plots=plots)
    except (ValueError, OSError, KeyError) as error:
        raise typer.BadParameter(str(error)) from error
    typer.echo(f"Analysis artifacts: {output.resolve()}")
