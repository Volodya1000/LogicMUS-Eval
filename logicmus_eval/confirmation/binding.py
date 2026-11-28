"""Technical logical-name → UUID binding, frozen before the first HTTP intent."""

import json
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from logicmus_eval.analysis.plan import AnalysisPlan
from logicmus_eval.confirmation.prospective import validate_template
from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.hashing import compute_file_sha256
from logicmus_eval.runner.config import RunConfig
from logicmus_eval.runner.journal import RunJournal, atomic_json
from logicmus_eval.runner.manifest import resume_preflight
from logicmus_eval.runner.preflight import digest
from logicmus_eval.runner.snapshot import read_snapshot


def substituted(template: AnalysisPlan, run_ids: dict[str, str]) -> AnalysisPlan:
    payload = template.model_dump(mode="json")
    for group in payload["groups"]:
        group["run_ids"] = [run_ids[name] for name in group["run_ids"]]
    return AnalysisPlan.model_validate(payload)


def bind_analysis(
    plan: ExperimentPlan,
    configs: dict[str, RunConfig],
    template: AnalysisPlan,
    runs: dict[str, Path],
    destination: Path,
) -> dict[str, Any]:
    validate_template(plan, configs, template)
    if runs.keys() != configs.keys():
        raise ValueError("Incomplete logical run binding")
    with ExitStack() as locks:
        ids, hashes = {}, {}
        for name, root in sorted(runs.items()):
            initial = json.loads(
                (root / "run.manifest.json").read_text(encoding="utf-8")
            )
            journal = locks.enter_context(
                RunJournal(root.resolve(), initial["manifest_sha256"], read_only=True)
            )
            manifest, _ = resume_preflight(root.resolve(), configs[name])
            if journal.events:
                raise ValueError(
                    "Binding must occur before first HTTP; journal is not empty"
                )
            ids[name] = manifest["payload"]["run_id"]
            hashes[name] = compute_file_sha256(root / "run.manifest.json")
        if len(set(ids.values())) != len(ids):
            raise ValueError("Distinct logical runs require distinct UUIDs")
        bound = substituted(template, ids)
        destination.mkdir(parents=True, exist_ok=False)
        atomic_json(destination / "analysis.bound.json", bound.model_dump(mode="json"))
        receipt = {
            "binding_version": "confirmation-binding-v1",
            "before_first_http": True,
            "bound_at": datetime.now(UTC).isoformat(),
            "template_sha256": digest(template.model_dump(mode="json")),
            "bound_sha256": compute_file_sha256(destination / "analysis.bound.json"),
            "run_ids": ids,
            "run_manifests": hashes,
        }
        atomic_json(destination / "binding.json", receipt)
    return receipt


def verify_binding(
    destination: Path, template: AnalysisPlan, runs: dict[str, Path]
) -> None:
    receipt = json.loads((destination / "binding.json").read_text(encoding="utf-8"))
    if (
        receipt["template_sha256"] != digest(template.model_dump(mode="json"))
        or receipt["before_first_http"] is not True
        or runs.keys() != receipt["run_ids"].keys()
        or receipt["bound_sha256"]
        != compute_file_sha256(destination / "analysis.bound.json")
    ):
        raise ValueError("Analysis binding integrity failed")
    bound = AnalysisPlan.model_validate_json(
        (destination / "analysis.bound.json").read_text(encoding="utf-8")
    )
    if bound != substituted(template, receipt["run_ids"]):
        raise ValueError("Analysis binding changed scientific content")
    for name, root in runs.items():
        saved = read_snapshot(root.resolve(), [root.resolve() / "report.json"])
        for state in saved.states.values():
            for attempt in state.attempts:
                if datetime.fromisoformat(attempt.intent.at) < datetime.fromisoformat(
                    receipt["bound_at"]
                ):
                    raise ValueError("HTTP attempt precedes analysis binding")
        if (
            saved.manifest.payload.run_id != receipt["run_ids"][name]
            or compute_file_sha256(root / "run.manifest.json")
            != receipt["run_manifests"][name]
        ):
            raise ValueError("Run identity differs from analysis binding")
