"""Gated orchestration delegates all execution and analysis to existing services."""

from pathlib import Path
from typing import Any

from logicmus_eval.confirmation.binding import bind_analysis
from logicmus_eval.confirmation.io import admission_files, check_admission
from logicmus_eval.confirmation.service import contracts, verify_release
from logicmus_eval.runner.execution import (
    Completion,
    IndeterminatePolicy,
    initialize_run,
    resume_run,
)
from logicmus_eval.runner.journal import atomic_json


def initialize_release(root: Path) -> dict[str, Any]:
    status = verify_release(root)
    if status["gates"]["ready_for_initialization"] != "passed":
        raise ValueError(
            "Release blocked before initialization: " + "; ".join(status["issues"])
        )
    if (root / "admission.json").exists():
        raise ValueError("Admission already fixed; resume the existing release")
    _, plan, configs, template = contracts(root)
    runs = {name: root / "bundle" / "runs" / name for name in configs}
    for name, config in configs.items():
        initialize_run(config, runs[name])
    receipt = bind_analysis(plan, configs, template, runs, root / "bundle" / "binding")
    admission = {
        "files": admission_files(root),
        "before_first_http": True,
        "binding": receipt,
        "gates": status["gates"],
    }
    atomic_json(root / "admission.json", admission)
    return admission


def resume_release(
    root: Path,
    name: str,
    *,
    completion: Completion | None = None,
    indeterminate_policy: IndeterminatePolicy = "halt",
) -> None:
    check_admission(root)
    status = verify_release(root)
    if status["gates"]["ready_for_scale"] != "passed":
        raise ValueError("Release blocked before HTTP: " + "; ".join(status["issues"]))
    configs = contracts(root)[2]
    if name not in configs:
        raise ValueError("Unknown logical run")
    resume_run(
        root / "bundle" / "runs" / name,
        config=configs[name],
        completion=completion,
        indeterminate_policy=indeterminate_policy,
    )
