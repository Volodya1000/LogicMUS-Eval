"""Offline freeze, integrity and separate admission gates. Never invokes inference."""

import platform
import subprocess
from importlib.metadata import version
from pathlib import Path
from typing import Any

from logicmus_eval.analysis.plan import AnalysisPlan
from logicmus_eval.confirmation.inventory import families, inventory
from logicmus_eval.confirmation.io import check_admission, local, read_json
from logicmus_eval.confirmation.models import ReleaseSpec
from logicmus_eval.confirmation.prospective import validate_template
from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.experiment_preparation import ExperimentManifest
from logicmus_eval.hashing import compute_file_sha256, compute_source_bundle_hash
from logicmus_eval.release import assert_controlled_series_approved
from logicmus_eval.runner.config import RunConfig, load_config
from logicmus_eval.runner.journal import atomic_json
from logicmus_eval.runner.preflight import digest, preflight


def contracts(
    root: Path,
) -> tuple[ReleaseSpec, ExperimentPlan, dict[str, RunConfig], AnalysisPlan]:
    spec = ReleaseSpec.model_validate_json(
        (root / "release.spec.json").read_text(encoding="utf-8")
    )
    plan = ExperimentPlan.model_validate_json(
        local(root, spec.plan).read_text(encoding="utf-8")
    )
    configs = {
        name: load_config(local(root, path)) for name, path in spec.configs.items()
    }
    if len({c.series_manifest for c in configs.values()}) != 1:
        raise ValueError("All logical runs must use the same confirmation manifest")
    for config in configs.values():
        if not Path(config.series_manifest).resolve().is_relative_to(root.resolve()):
            raise ValueError("Series bundle must stay within the portable release root")
        if config.diagnostic_parent_run is not None:
            raise ValueError("Confirmation release cannot select diagnostic reruns")
        if config.infrastructure_smoke is not None:
            raise ValueError("Infrastructure smoke cannot establish datasets_admitted")
    template = AnalysisPlan.model_validate_json(
        local(root, spec.analysis_template).read_text(encoding="utf-8")
    )
    validate_template(plan, configs, template)
    return spec, plan, configs, template


def environment() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        **{
            name: version(name)
            for name in (
                "pydantic",
                "z3-solver",
                "numpy",
                "scikit-learn",
                "typer",
                "litellm",
                "tenacity",
                "pandas",
                "matplotlib",
            )
        },
    }


def _repository() -> Path:
    return Path(__file__).resolve().parents[2]


def freeze_release(root: Path) -> dict[str, Any]:
    """Create once, before preparation; never silently re-freeze changed science."""
    spec, plan, configs, template = contracts(root)
    manifest_path = root / "release.manifest.json"
    if manifest_path.exists():
        raise ValueError(
            "Release already frozen; scientific changes require a new release version"
        )
    dev_families: set[str] = set()
    for name in spec.development_plans:
        development = ExperimentPlan.model_validate_json(
            local(root, name).read_text(encoding="utf-8")
        )
        if development.purpose != "development":
            raise ValueError("Development reference must have development purpose")
        dev_families |= families(development)
    smoke = ExperimentPlan.model_validate_json(
        local(root, spec.smoke_plan).read_text(encoding="utf-8")
    )
    if smoke.purpose != "development":
        raise ValueError("Smoke must use development families")
    if spec.smoke_selection_rule is not None:
        from logicmus_eval.infrastructure_smoke import (  # pylint: disable=import-outside-toplevel
            SelectionRule,
        )

        rule = SelectionRule.model_validate_json(
            local(root, spec.smoke_selection_rule).read_text(encoding="utf-8")
        )
        if rule.seed not in smoke.seeds or rule.pair_index >= smoke.pairs_per_seed:
            raise ValueError("Smoke selection is outside the frozen development parent")
    if plan.purpose == "confirmation" and families(plan) & (
        dev_families | families(smoke)
    ):
        raise ValueError("Development/confirmation family overlap")
    paths = {
        "release.spec.json",
        spec.plan,
        spec.protocol,
        spec.analysis_template,
        spec.smoke_plan,
        *spec.configs.values(),
        *spec.development_plans,
        *spec.supporting_files,
    }
    if spec.smoke_selection_rule is not None:
        paths.add(spec.smoke_selection_rule)
    files = {p: compute_file_sha256(local(root, p)) for p in sorted(paths)}
    payload = {
        "release_id": spec.release_id,
        "base_commit": spec.base_commit,
        "files": files,
        "plan_sha256": plan.plan_hash,
        "analysis_template_sha256": digest(template.model_dump(mode="json")),
        "source_bundle_sha256": compute_source_bundle_hash(),
        "source_git_head": git_head(),
        "preparation_receipt": "preparation.json",
        "operator_evidence": ["backend.evidence.json", "smoke.evidence.json"],
        "binding_receipt": "bundle/binding/binding.json",
        "admission_receipt": "admission.json",
        "dependency_lock_sha256": compute_file_sha256(_repository() / "uv.lock"),
        "environment": environment(),
        "inventory": inventory(plan, configs),
        "contrast_pairs": validate_template(plan, configs, template),
        "development_confirmation_overlap": 0,
        "protocols": {
            "generation": plan.protocol_version,
            "runner": "controlled-run-v1",
            "analysis": "controlled-analysis-v1",
        },
    }
    atomic_json(manifest_path, {"payload": payload, "sha256": digest(payload)})
    return payload


def _check_freeze(root: Path) -> dict[str, Any]:
    frozen = read_json(root / "release.manifest.json")
    payload: dict[str, Any] = frozen["payload"]
    if frozen["sha256"] != digest(payload):
        raise ValueError("Release manifest checksum differs")
    for name, checksum in payload["files"].items():
        if compute_file_sha256(local(root, name)) != checksum:
            raise ValueError(
                f"Frozen artifact changed: {name}; create a new release version"
            )
    if payload["source_bundle_sha256"] != compute_source_bundle_hash():
        raise ValueError("Frozen source bundle changed")
    if payload["dependency_lock_sha256"] != compute_file_sha256(
        _repository() / "uv.lock"
    ):
        raise ValueError("Frozen dependency lock changed")
    if payload["environment"] != environment():
        raise ValueError("Frozen dependency environment changed")
    return payload


def seal_preparation(root: Path) -> dict[str, Any]:
    """Seal every saved byte, including failed checks. No generation or retry."""
    _check_freeze(root)
    _, plan, configs, _ = contracts(root)
    receipt = root / "preparation.json"
    if receipt.exists():
        raise ValueError("Preparation already sealed; retain the original attempt")
    manifest_path = Path(next(iter(configs.values())).series_manifest)
    manifest = ExperimentManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if manifest.plan_sha256 != plan.plan_hash:
        raise ValueError("Prepared plan differs from frozen plan")
    directory = manifest_path.parent
    artifacts = {
        p.relative_to(root.resolve()).as_posix(): compute_file_sha256(p)
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }
    payload = {
        "attempt": 1,
        "plan_sha256": plan.plan_hash,
        "source_bundle_sha256": manifest.source_bundle_sha256,
        "environment": manifest.environment,
        "artifacts": artifacts,
        "ready_for_evaluation": manifest.ready_for_evaluation,
        "failures": manifest.failures,
        "combined_acceptance": manifest.combined_acceptance.model_dump()
        if manifest.combined_acceptance
        else None,
        "cells": [
            {
                "cell": item.cell.model_dump(),
                "smt_passed": item.smt_passed,
                "reference_passed": item.reference_passed,
                "failures": item.failures,
                "leakage_acceptance": item.leakage_acceptance.model_dump()
                if item.leakage_acceptance
                else None,
            }
            for item in manifest.cells
        ],
    }
    atomic_json(receipt, {"payload": payload, "sha256": digest(payload)})
    return payload


def _check_preparation(
    root: Path,
    plan: ExperimentPlan,
    configs: dict[str, RunConfig],
    frozen: dict[str, Any],
) -> None:
    receipt = read_json(root / "preparation.json")
    payload = receipt["payload"]
    if (
        receipt["sha256"] != digest(payload)
        or payload["plan_sha256"] != plan.plan_hash
        or payload["source_bundle_sha256"] != frozen["source_bundle_sha256"]
    ):
        raise ValueError("Preparation receipt or source differs from freeze")
    for name, checksum in payload["artifacts"].items():
        if compute_file_sha256(local(root, name)) != checksum:
            raise ValueError(f"Prepared artifact changed: {name}")
    for config in configs.values():
        manifest = assert_controlled_series_approved(Path(config.series_manifest))
        if manifest.plan_sha256 != plan.plan_hash or manifest.plan != plan.normalized():
            raise ValueError("Dataset plan differs from frozen confirmation plan")
        ready = preflight(config)
        if len(ready.jobs) != inventory(plan, {"run": config})["requests"]:
            raise ValueError("Runner inventory differs from release counts")


def _profile_unknowns(configs: dict[str, RunConfig]) -> list[str]:
    unknowns = []
    placeholders = ("replace", "placeholder", "unknown", "todo", "tbd", "<", ">")
    for name, config in configs.items():
        for model in config.models:
            values = model.expected_profile.model_dump()
            # An available revision OR an exact file is sufficient; other fields mandatory.
            required = [k for k in values if k not in {"revision", "model_file"}]
            if not values["revision"] and not values["model_file"]:
                unknowns.append(
                    f"{name}/{model.model_id}: revision or model_file unknown"
                )
            for key in required:
                if values[key] is None or values[key] == "":
                    unknowns.append(f"{name}/{model.model_id}: {key} unknown")
            for key, value in {"model_id": model.model_id, **values}.items():
                if isinstance(value, str) and any(
                    p in value.lower() for p in placeholders
                ):
                    unknowns.append(f"{name}/{key}: placeholder")
    return unknowns


# The gates intentionally remain visible in one offline orchestration function.
# pylint: disable=too-many-locals
def verify_release(root: Path) -> dict[str, Any]:
    """Report separate gates; technical data success never means paper readiness."""
    statuses = {
        "scientific_plan_frozen": "blocked",
        "datasets_admitted": "blocked",
        "configurations_complete": "blocked",
        "backend_model_verified": "not_verified",
        "real_smoke": "not_verified",
        "analysis_bound": "not_verified",
        "ready_for_initialization": "blocked",
        "ready_for_scale": "blocked",
    }
    errors: list[str] = []
    try:
        frozen = _check_freeze(root)
        spec, plan, configs, template = contracts(root)
        if frozen["inventory"] != inventory(plan, configs):
            raise ValueError("Frozen inventory differs")
        statuses["scientific_plan_frozen"] = "passed"
    except (ValueError, OSError, KeyError) as error:
        return {"status": "blocked", "gates": statuses, "issues": [str(error)]}
    try:
        _check_preparation(root, plan, configs, frozen)
        statuses["datasets_admitted"] = "passed"
    except (ValueError, OSError, KeyError) as error:
        errors.append(str(error))
    unknowns = _profile_unknowns(configs)
    errors.extend(unknowns)
    if not unknowns:
        statuses["configurations_complete"] = "passed"
    # Evidence verification is deliberately separate from the saved RunConfig assertions.
    from logicmus_eval.confirmation.evidence import (  # pylint: disable=import-outside-toplevel
        check_backend,
        check_smoke,
    )

    for gate, checker in (
        ("backend_model_verified", check_backend),
        ("real_smoke", check_smoke),
    ):
        try:
            checker(root, spec, configs)
            statuses[gate] = "passed"
        except (ValueError, OSError, KeyError) as error:
            errors.append(f"{gate}: {error}")
    admission_gates = (
        "scientific_plan_frozen",
        "datasets_admitted",
        "configurations_complete",
        "backend_model_verified",
        "real_smoke",
    )
    if all(statuses[k] == "passed" for k in admission_gates):
        statuses["ready_for_initialization"] = "passed"
    binding = root / "bundle" / "binding"
    if binding.exists():
        from logicmus_eval.confirmation.binding import (  # pylint: disable=import-outside-toplevel
            verify_binding,  # pylint: disable=import-outside-toplevel
        )

        try:
            verify_binding(
                binding,
                template,
                {name: root / "bundle" / "runs" / name for name in configs},
            )
            statuses["analysis_bound"] = "passed"
        except (ValueError, OSError, KeyError) as error:
            errors.append(str(error))
    if (
        statuses["ready_for_initialization"] == "passed"
        and statuses["analysis_bound"] == "passed"
    ):
        try:
            check_admission(root)
            statuses["ready_for_scale"] = "passed"
        except (ValueError, OSError, KeyError) as error:
            errors.append(str(error))
    return {
        "status": "ready" if statuses["ready_for_scale"] == "passed" else "blocked",
        "gates": statuses,
        "issues": errors,
        "inventory": frozen["inventory"],
    }


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=_repository(), text=True
    ).strip()
