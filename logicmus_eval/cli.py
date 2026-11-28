"""LogicMUS-Eval CLI layer built on top of Typer.

Usage:
    python -m logicmus_eval.cli generate --mus-size-min 2 --mus-size-max 5 --pairs-per-group 25
    python -m logicmus_eval.cli evaluate --strategy direct --limit 10
"""

import typer

from logicmus_eval.commands.analyze import controlled
from logicmus_eval.commands.confirmation import check_release, freeze, seal
from logicmus_eval.commands.confirmation import initialize as initialize_release
from logicmus_eval.commands.confirmation import resume as resume_release
from logicmus_eval.commands.evaluate import evaluate
from logicmus_eval.commands.generate import generate
from logicmus_eval.commands.infrastructure_smoke import check_smoke_evidence
from logicmus_eval.commands.prepare_experiment import prepare
from logicmus_eval.commands.prepare_smoke import prepare_smoke
from logicmus_eval.commands.run_experiment import check, initialize, resume, start

app = typer.Typer(
    name="logicmus-eval",
    help="LogicMUS-Eval: dataset generation and LLM evaluation.",
    no_args_is_help=True,
    add_completion=False,
)

app.command(name="generate")(generate)
app.command(name="evaluate")(evaluate)
app.command(name="prepare-experiment")(prepare)
app.command(name="prepare-infrastructure-smoke")(prepare_smoke)
app.command(name="check-development-smoke")(check_smoke_evidence)
app.command(name="experiment-preflight")(check)
app.command(name="experiment-start")(start)
app.command(name="experiment-initialize")(initialize)
app.command(name="experiment-resume")(resume)
app.command(name="analyze-controlled")(controlled)
app.command(name="release-freeze")(freeze)
app.command(name="release-check")(check_release)
app.command(name="release-seal-preparation")(seal)
app.command(name="release-initialize")(initialize_release)
app.command(name="release-resume")(resume_release)

if __name__ == "__main__":
    app()
