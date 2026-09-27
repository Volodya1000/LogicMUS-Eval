import datetime
from typing import Annotated

import typer

from src.evaluate_llm import run_evaluation
from src.logging_utils import configure_logging


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
        str | None,
        typer.Option(
            "--output-file", help="Report file name. Auto-generated if not provided."
        ),
    ] = None,
) -> None:
    """Evaluate an LLM on the generated dataset."""
    if strategy not in {"direct", "z3"}:
        typer.echo("Error: strategy must be 'direct' or 'z3'", err=True)
        raise typer.Exit(1)

    configure_logging()

    if output_file is None:
        safe_model = model_name.replace("/", "_").replace(":", "_")
        timestamp = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d_%H%M%S")
        output_file = f"eval_{safe_model}_{strategy}_{timestamp}.json"

    run_evaluation(
        dataset_dir=dataset_dir,
        model_name=model_name,
        strategy_name=strategy,
        limit=limit,
        output_file=output_file,
    )
