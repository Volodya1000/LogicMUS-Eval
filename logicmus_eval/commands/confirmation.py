"""Explicit offline release commands; only release-resume can contact models."""

import json
from pathlib import Path
from typing import Annotated

import typer

from logicmus_eval.confirmation.service import (
    freeze_release,
    seal_preparation,
    verify_release,
)


def freeze(root: Annotated[Path, typer.Option("--release-dir")]) -> None:
    try:
        typer.echo(
            json.dumps(freeze_release(root.resolve()), ensure_ascii=False, indent=2)
        )
    except (ValueError, OSError) as error:
        typer.echo(f"Freeze rejected: {error}", err=True)
        raise typer.Exit(1) from error


def check_release(root: Annotated[Path, typer.Option("--release-dir")]) -> None:
    status = verify_release(root.resolve())
    typer.echo(json.dumps(status, ensure_ascii=False, indent=2))
    if status["status"] != "ready":
        raise typer.Exit(1)


def seal(root: Annotated[Path, typer.Option("--release-dir")]) -> None:
    try:
        payload = seal_preparation(root.resolve())
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        if not payload["ready_for_evaluation"]:
            raise typer.Exit(1)
    except (ValueError, OSError) as error:
        typer.echo(f"Preparation seal rejected: {error}", err=True)
        raise typer.Exit(1) from error


def initialize(root: Annotated[Path, typer.Option("--release-dir")]) -> None:
    # pylint: disable=import-outside-toplevel
    from logicmus_eval.confirmation.launch import (
        initialize_release,  # pylint: disable=import-outside-toplevel
    )

    try:
        initialize_release(root.resolve())
        typer.echo("Admission and AnalysisPlan binding fixed before HTTP")
    except (ValueError, OSError) as error:
        typer.echo(f"Release initialization rejected: {error}", err=True)
        raise typer.Exit(1) from error


def resume(
    root: Annotated[Path, typer.Option("--release-dir")],
    name: Annotated[str, typer.Option("--logical-run")],
    indeterminate_policy: Annotated[
        str, typer.Option("--indeterminate-policy")
    ] = "halt",
) -> None:
    # pylint: disable=import-outside-toplevel
    from logicmus_eval.confirmation.launch import (
        resume_release,  # pylint: disable=import-outside-toplevel
    )

    try:
        if indeterminate_policy not in {"halt", "retry"}:
            raise ValueError("indeterminate-policy must be halt or retry")
        resume_release(
            root.resolve(),
            name,
            indeterminate_policy="retry" if indeterminate_policy == "retry" else "halt",
        )
        typer.echo(f"Logical run completed: {name}")
    except (ValueError, OSError) as error:
        typer.echo(f"Release execution stopped: {error}", err=True)
        raise typer.Exit(1) from error
