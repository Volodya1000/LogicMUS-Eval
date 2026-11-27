"""Offline inspection and explicit controlled execution CLI boundaries."""

import json
from pathlib import Path
from typing import Annotated

import typer

from logicmus_eval.runner.config import load_config
from logicmus_eval.runner.journal import RunJournal
from logicmus_eval.runner.manifest import resume_preflight
from logicmus_eval.runner.preflight import preflight
from logicmus_eval.runner.state import replay


def check(
    config: Annotated[Path | None, typer.Option("--config")] = None,
    run_dir: Annotated[Path | None, typer.Option("--run-dir")] = None,
) -> None:
    """OFFLINE: validate series, inventory, budgets and optional resume compatibility."""
    try:
        selected = load_config(config) if config else None
        state_counts = None
        if run_dir is not None:
            manifest, ready = resume_preflight(run_dir.resolve(), selected)
            with RunJournal(run_dir.resolve(), manifest["manifest_sha256"]) as journal:
                states = replay(journal.events, ready.jobs)
                state_counts = {
                    "finalized": sum(
                        state.outcome is not None for state in states.values()
                    ),
                    "pending": sum(not state.attempts for state in states.values()),
                    "indeterminate": sum(
                        state.indeterminate for state in states.values()
                    ),
                }
        elif selected:
            ready = preflight(selected)
        else:
            raise ValueError("Supply --config or --run-dir")
        typer.echo(
            json.dumps(
                {
                    "ready": True,
                    "jobs": len(ready.jobs),
                    "counts": ready.counts,
                    "identity_sha256": ready.identity_hash,
                    "resume": state_counts,
                    "config": ready.config.model_dump(mode="json"),
                    "unknown_or_unconfirmed": ready.unknowns,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    except (ValueError, OSError) as error:
        typer.echo(f"Preflight failed: {error}", err=True)
        raise typer.Exit(1) from error


def start(
    config: Annotated[Path, typer.Option("--config")],
    run_dir: Annotated[Path, typer.Option("--run-dir")],
) -> None:
    """Start a NEW run in a directory that does not yet exist (contacts the model)."""
    # pylint: disable=import-outside-toplevel
    from logicmus_eval.runner.execution import (
        new_run,  # pylint: disable=import-outside-toplevel
    )

    try:
        report = new_run(load_config(config), run_dir)
        typer.echo(
            f"{report.status}: {len(report.details)} finalized; {run_dir / 'report.json'}"
        )
    except (ValueError, OSError) as error:
        typer.echo(f"Run stopped: {error}", err=True)
        raise typer.Exit(1) from error


def resume(
    run_dir: Annotated[Path, typer.Option("--run-dir")],
    config: Annotated[Path | None, typer.Option("--config")] = None,
    indeterminate_policy: Annotated[
        str, typer.Option("--indeterminate-policy")
    ] = "halt",
) -> None:
    """Resume saved conditions. Unresolved HTTP halts until explicit retry permission."""
    # pylint: disable=import-outside-toplevel
    from logicmus_eval.runner.execution import (
        resume_run,  # pylint: disable=import-outside-toplevel
    )

    try:
        if indeterminate_policy not in {"halt", "retry"}:
            raise ValueError("indeterminate-policy must be halt or retry")
        report = resume_run(
            run_dir,
            config=load_config(config) if config else None,
            indeterminate_policy="retry" if indeterminate_policy == "retry" else "halt",
        )
        typer.echo(
            f"{report.status}: {len(report.details)} finalized; {run_dir / 'report.json'}"
        )
    except (ValueError, OSError) as error:
        typer.echo(f"Resume stopped: {error}", err=True)
        raise typer.Exit(1) from error
