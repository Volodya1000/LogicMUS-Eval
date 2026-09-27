"""LogicMUS-Eval CLI layer built on top of Typer.

Usage:
    python -m src.cli generate --mus-size-min 2 --mus-size-max 5 --pairs-per-group 25
    python -m src.cli evaluate --strategy direct --limit 10
"""

import typer

from src.commands.evaluate import evaluate
from src.commands.generate import generate

app = typer.Typer(
    name="logicmus-eval",
    help="LogicMUS-Eval: dataset generation and LLM evaluation.",
    no_args_is_help=True,
    add_completion=False,
)

app.command(name="generate")(generate)
app.command(name="evaluate")(evaluate)

if __name__ == "__main__":
    app()
