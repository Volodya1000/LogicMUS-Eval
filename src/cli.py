"""LogicMUS-Eval CLI layer built on top of Typer.

Usage:
    python -m src.cli generate --mus-sizes 2 --mus-sizes 3 --pairs-per-group 25
    python -m src.cli evaluate --strategy direct --limit 10
"""

import logging
from typing import Annotated

import typer

from src.evaluate_llm import run_evaluation
from src.run_pipeline import GenerationConfig, run_generation

app = typer.Typer(
    name="logicmus-eval",
    help="LogicMUS-Eval: dataset generation and LLM evaluation.",
    no_args_is_help=True,
    add_completion=False,
)

_DEFAULT_MUS_SIZES: tuple[int, ...] = (2, 3, 4, 5)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


@app.command()
def generate(
    mus_sizes: Annotated[
        list[int] | None,
        typer.Option(
            "--mus-sizes",
            help="MUS sizes (repeat flag: --mus-sizes 2 --mus-sizes 3).",
        ),
    ] = None,
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
    _configure_logging()
    config = GenerationConfig(
        mus_sizes=list(mus_sizes) if mus_sizes else list(_DEFAULT_MUS_SIZES),
        pairs_per_group=pairs_per_group,
        total_rules=total_rules,
        base_seed=base_seed,
        output_dir=output_dir,
    )
    run_generation(config)


@app.command()
def evaluate(
    dataset_dir: Annotated[
        str,
        typer.Option("--dataset-dir", help="Directory with the dataset."),
    ] = "data/generated_cases",
    model_name: Annotated[
        str,
        typer.Option("--model-name", help="LLM identifier."),
    ] = "openai/qwen2.5-coder-14b-instruct",
    strategy: Annotated[
        str,
        typer.Option("--strategy", help="Evaluation strategy: 'direct' or 'z3'."),
    ] = "direct",
    limit: Annotated[
        int,
        typer.Option("--limit", help="Number of cases to process."),
    ] = 10,
    output_file: Annotated[
        str,
        typer.Option("--output-file", help="Report file name."),
    ] = "evaluation_results.json",
) -> None:
    """Evaluate an LLM on the generated dataset."""
    if strategy not in {"direct", "z3"}:
        raise typer.BadParameter("strategy must be 'direct' or 'z3'")

    _configure_logging()
    run_evaluation(
        dataset_dir=dataset_dir,
        model_name=model_name,
        strategy_name=strategy,
        limit=limit,
        output_file=output_file,
    )


if __name__ == "__main__":
    app()
