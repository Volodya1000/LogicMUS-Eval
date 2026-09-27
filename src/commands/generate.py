from typing import Annotated

import typer

from src.logging_utils import configure_logging
from src.run_pipeline import GenerationConfig, run_generation

# pylint: disable=too-many-arguments, too-many-positional-arguments


def generate(
    mus_size_min: Annotated[
        int,
        typer.Option(
            "--mus-size-min",
            help="Minimum MUS size.",
        ),
    ] = 2,
    mus_size_max: Annotated[
        int,
        typer.Option(
            "--mus-size-max",
            help="Maximum MUS size.",
        ),
    ] = 5,
    pairs_per_group: Annotated[
        int,
        typer.Option("--pairs-per-group", help="SAT/UNSAT pairs per MUS size."),
    ] = 25,
    total_rules: Annotated[
        int,
        typer.Option("--total-rules", help="Total number of rules per case."),
    ] = 20,
    base_seed: Annotated[
        int,
        typer.Option("--base-seed", help="Base random seed."),
    ] = 42,
    output_dir: Annotated[
        str,
        typer.Option("--output-dir", help="Output directory for artifacts."),
    ] = "data/generated_cases",
) -> None:
    """Generate, verify and save the LogicMUS-Eval dataset."""
    configure_logging()

    if mus_size_min > mus_size_max:
        typer.echo("Error: mus-size-min cannot be greater than mus-size-max", err=True)
        raise typer.Exit(1)
    if mus_size_max > total_rules:
        typer.echo("Error: mus-size-max cannot be greater than total-rules", err=True)
        raise typer.Exit(1)

    config = GenerationConfig(
        mus_sizes=list(range(mus_size_min, mus_size_max + 1)),
        pairs_per_group=pairs_per_group,
        total_rules=total_rules,
        base_seed=base_seed,
        output_dir=output_dir,
    )
    run_generation(config)
