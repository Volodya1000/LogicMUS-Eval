"""Small offline candidate receipt; never a release manifest or admission.

Run from the repository root with ``python -m scripts.confirmation_candidate``.
Existing release and preparation implementations are unchanged. Exclusive files
protect against accidental overwrite/retry, not malicious filesystem owners.
"""

import argparse
import json
import os
import platform
from datetime import UTC, datetime
from importlib.metadata import distributions
from pathlib import Path
from typing import Any

from logicmus_eval.analysis.plan import AnalysisPlan
from logicmus_eval.confirmation.inventory import inventory
from logicmus_eval.confirmation.prospective import validate_template
from logicmus_eval.confirmation.service import environment
from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.experiment_preparation import prepare_experiment
from logicmus_eval.hashing import compute_file_sha256, compute_source_bundle_hash
from logicmus_eval.runner.config import RunConfig, load_config
from logicmus_eval.runner.preflight import digest

REPOSITORY = Path(__file__).resolve().parents[1]
CONTRACTS = (
    "confirmation.plan.json",
    "analysis.template.json",
    "protocol.md",
    "qwen.proposed.json",
    "gemma.proposed.json",
    "gpt-oss.proposed.json",
    "model-facts.json",
    "inventory.before-preparation.json",
    "origin-inventory.json",
    "identity-migration.json",
    "prospective-validation.json",
    "development.reference.json",
    "development.parent.plan.json",
)


def _exclusive(path: Path, payload: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _not_release(root: Path) -> None:
    for name in ("release.manifest.json", "release.spec.json", "admission.json"):
        if (root / name).exists():
            raise ValueError(
                f"Candidate cannot contain executable release file: {name}"
            )


def _inputs(repository: Path) -> dict[str, str]:
    paths = sorted((repository / "logicmus_eval").rglob("*.py"))
    if not paths:
        raise ValueError("Empty source inventory")
    paths += [
        repository / "scripts" / "confirmation_candidate.py",
        repository / "uv.lock",
        repository / "pyproject.toml",
    ]
    return {p.relative_to(repository).as_posix(): compute_file_sha256(p) for p in paths}


def _environment() -> dict[str, Any]:
    return {
        "project": environment(),
        "platform": platform.platform(),
        "installed_distributions": sorted(
            [
                {"name": dist.metadata["Name"], "version": dist.version}
                for dist in distributions()
            ],
            key=lambda item: (item["name"], item["version"]),
        ),
    }


def _contracts(root: Path) -> tuple[ExperimentPlan, dict[str, RunConfig], AnalysisPlan]:
    plan = ExperimentPlan.model_validate_json(
        (root / "confirmation.plan.json").read_text(encoding="utf-8")
    )
    if plan.protocol_version != "controlled-v2" or plan.purpose != "confirmation":
        raise ValueError("Expected controlled-v2 confirmation scientific candidate")
    configs = {
        name: load_config(root / f"{name}.proposed.json")
        for name in ("qwen", "gemma", "gpt-oss")
    }
    analysis = AnalysisPlan.model_validate_json(
        (root / "analysis.template.json").read_text(encoding="utf-8")
    )
    validate_template(plan, configs, analysis)
    if json.loads(
        (root / "inventory.before-preparation.json").read_text(encoding="utf-8")
    ) != inventory(plan, configs):
        raise ValueError("Initial inventory differs from prospective contracts")
    return plan, configs, analysis


def freeze(root: Path, repository: Path = REPOSITORY) -> dict[str, Any]:
    _not_release(root)
    if (root / "bundle").exists() or (root / "preparation.attempt.json").exists():
        raise ValueError("Candidate must be frozen before preparation")
    plan, configs, analysis = _contracts(root)
    payload = {
        "receipt_version": "confirmation-v2-candidate-v1",
        "kind": "scientific-candidate-only",
        "release_admission": False,
        "frozen_at": datetime.now(UTC).isoformat(),
        "files": {name: compute_file_sha256(root / name) for name in CONTRACTS},
        "repository_inputs": _inputs(repository),
        "source_bundle_sha256": compute_source_bundle_hash(),
        "environment": _environment(),
        "plan_sha256": plan.plan_hash,
        "analysis_sha256": digest(analysis.model_dump(mode="json")),
        "inventory": inventory(plan, configs),
    }
    _exclusive(
        root / "candidate.receipt.json", {"payload": payload, "sha256": digest(payload)}
    )
    return payload


def verify(root: Path, repository: Path = REPOSITORY) -> dict[str, Any]:
    _not_release(root)
    receipt = json.loads((root / "candidate.receipt.json").read_text(encoding="utf-8"))
    payload: dict[str, Any] = receipt["payload"]
    if (
        receipt["sha256"] != digest(payload)
        or payload["kind"] != "scientific-candidate-only"
        or payload["release_admission"] is not False
    ):
        raise ValueError("Candidate receipt changed or claims release admission")
    if set(payload["files"]) != set(CONTRACTS):
        raise ValueError("Candidate contract inventory changed")
    for name, checksum in payload["files"].items():
        if compute_file_sha256(root / name) != checksum:
            raise ValueError(f"Candidate input changed: {name}")
    if (
        payload["repository_inputs"] != _inputs(repository)
        or payload["source_bundle_sha256"] != compute_source_bundle_hash()
    ):
        raise ValueError("Candidate source/helper/dependencies changed")
    if payload["environment"] != _environment():
        raise ValueError("Candidate dependency environment changed")
    _contracts(root)
    return payload


def begin_preparation(root: Path, repository: Path = REPOSITORY) -> dict[str, Any]:
    payload = verify(root, repository)
    if (root / "bundle").exists():
        raise ValueError("Existing preparation output; never overwrite or retry")
    attempt = {
        "attempt": 1,
        "started_at": datetime.now(UTC).isoformat(),
        "candidate_receipt_sha256": compute_file_sha256(
            root / "candidate.receipt.json"
        ),
        "plan_sha256": payload["plan_sha256"],
        "source_bundle_sha256": payload["source_bundle_sha256"],
        "command": "production prepare_experiment(plan, root / 'bundle/confirmation')",
    }
    _exclusive(root / "preparation.attempt.json", attempt)
    return attempt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "verify", "prepare"))
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    if args.action == "freeze":
        result = freeze(root)
    elif args.action == "verify":
        result = verify(root)
    else:
        begin_preparation(root)
        plan, _, _ = _contracts(root)
        manifest = prepare_experiment(plan, root / "bundle" / "confirmation")
        result = {
            "attempt": 1,
            "finished_at": datetime.now(UTC).isoformat(),
            "ready_for_evaluation": manifest.ready_for_evaluation,
            "manifest_sha256": compute_file_sha256(
                root / "bundle/confirmation/series.manifest.json"
            ),
        }
        _exclusive(root / "preparation.finished.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
