"""Offline preparation with persistent diagnostics and fail-closed readiness."""

import json
import platform
from pathlib import Path
from typing import Any

import numpy as np
import sklearn  # type: ignore[import-untyped]
import z3  # type: ignore[import-untyped]
from pydantic import Field

from logicmus_eval.controlled_generation import generate_cell
from logicmus_eval.experiment_plan import (
    ExperimentCell,
    ExperimentPlan,
    PlanModel,
    case_identity,
)
from logicmus_eval.hashing import compute_file_sha256, compute_source_bundle_hash
from logicmus_eval.independent_smt import reference_check, smt_script
from logicmus_eval.leakage import calculate_leakage
from logicmus_eval.models.manifests import LeakageAcceptance
from logicmus_eval.models.pipeline import LeakageReport
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.storage import FileStorageManager
from logicmus_eval.verifier import build_z3_solver, verify_case

SERIES_MANIFEST = "series.manifest.json"


class CellPreparation(PlanModel):  # pylint: disable=too-many-instance-attributes
    cell: ExperimentCell
    dataset_path: str | None = None
    dataset_sha256: str | None = None
    reference_path: str | None = None
    reference_sha256: str | None = None
    smt_checks: list[dict[str, Any]] = Field(default_factory=list)
    reference_checks: list[dict[str, Any]] = Field(default_factory=list)
    smt_passed: bool = False
    reference_passed: bool = False
    leakage_report: LeakageReport | None = None
    leakage_acceptance: LeakageAcceptance | None = None
    failures: list[str] = Field(default_factory=list)


class ExperimentManifest(PlanModel):
    manifest_version: str = "controlled-v1"
    plan: dict[str, Any]
    plan_sha256: str
    source_bundle_sha256: str
    environment: dict[str, str]
    cells: list[CellPreparation]
    combined_path: str | None = None
    combined_sha256: str | None = None
    combined_leakage: LeakageReport | None = None
    combined_acceptance: LeakageAcceptance | None = None
    cv_grouping: str = "family_id"
    ready_for_evaluation: bool = False
    failures: list[str] = Field(default_factory=list)


def _accept(
    report: LeakageReport, plan: ExperimentPlan, ks: list[int]
) -> LeakageAcceptance:
    result = report.acceptance(plan.leakage_threshold, ks, ("direct", "z3"))
    result.cv_grouping = "family_id"
    return result


def _expected_cases(plan: ExperimentPlan, cell: ExperimentCell) -> dict[str, bool]:
    return {
        case_identity(cell, seed, index, is_sat, plan.protocol_version): is_sat
        for seed in plan.seeds
        for index in range(plan.pairs_per_seed)
        for is_sat in (True, False)
    }


def _records_match(checks: list[dict[str, Any]], expected: dict[str, bool]) -> bool:
    ids = [check.get("case_id") for check in checks]
    return (
        len(ids) == len(expected)
        and all(isinstance(uid, str) for uid in ids)
        and set(ids) == set(expected)
        and all(check.get("passed") is True for check in checks)
    )


def _smt_evidence(
    checks: list[dict[str, Any]], expected: dict[str, bool], k: int
) -> bool:
    if not _records_match(checks, expected):
        return False
    for check in checks:
        if not all(
            check.get(key) is True
            for key in (
                "exact_k_n",
                "serialized_matches",
                "unique_mus",
                "is_sat_correct",
                "is_mus_valid",
                "is_mus_minimal",
            )
        ):
            return False
        core = check.get("extracted_core_ids")
        gold = check.get("expected_core_ids")
        if not isinstance(core, list) or not isinstance(gold, list):
            return False
        if not all(isinstance(rid, str) for rid in core + gold):
            return False
        if (
            len(core) != len(set(core))
            or set(core) != set(gold)
            or len(core) != (0 if expected[check["case_id"]] else k)
        ):
            return False
    return True


def _reference_evidence(
    checks: list[dict[str, Any]], expected: dict[str, bool]
) -> bool:
    return _records_match(checks, expected) and all(
        check.get("status") == ("sat" if expected[check["case_id"]] else "unsat")
        for check in checks
    )


def _read_serialized(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


# pylint: disable=too-many-locals
def _verify_cell(
    dataset: list[LogicTestCase],
    artifact: CellPreparation,
    serialized: list[dict[str, Any]],
) -> dict[str, str]:
    scripts = {}
    for index, case in enumerate(dataset):
        try:
            matches = index < len(serialized) and serialized[index] == json.loads(
                case.model_dump_json()
            )
            if not matches:
                artifact.failures.append(
                    f"serialized dataset differs from generated case: {case.case_id}"
                )
            result = verify_case(case)
            result.extracted_core_ids.sort()
            exact = (
                len(case.rules) == artifact.cell.n
                and len({r.id for r in case.rules}) == artifact.cell.n
                and case.mus_size == artifact.cell.k
                and len(set(case.mus_expected))
                == (0 if case.is_satisfiable else artifact.cell.k)
            )
            unique = case.is_satisfiable or all(
                build_z3_solver([r for r in case.rules if r.id != rid]).check()
                == z3.sat
                for rid in case.mus_expected
            )
            passed = (
                matches
                and exact
                and unique
                and all(
                    (
                        result.is_sat_correct,
                        result.is_mus_valid,
                        result.is_mus_minimal,
                    )
                )
            )
            artifact.smt_checks.append(
                {
                    "case_id": case.case_id,
                    "exact_k_n": exact,
                    "serialized_matches": matches,
                    "unique_mus": unique,
                    "expected_core_ids": sorted(case.mus_expected),
                    **result.model_dump(),
                    "passed": passed,
                }
            )
            if not passed:
                artifact.failures.append(f"SMT validation failed: {case.case_id}")
        except Exception as error:  # noqa: BLE001 # pylint: disable=broad-exception-caught
            artifact.smt_checks.append(
                {"case_id": case.case_id, "passed": False, "error": str(error)}
            )
            artifact.failures.append(f"SMT validation error: {case.case_id}: {error}")
    for payload in serialized:
        uid = str(payload.get("case_id", "<missing>"))
        try:
            # Read the actual hashed JSONL, independently of the writer/to_dict.
            scripts[uid] = smt_script(payload["rules"])
            check = reference_check(payload)
            artifact.reference_checks.append(check)
            if not check["passed"]:
                artifact.failures.append(f"Independent SMT control failed: {uid}")
        except Exception as error:  # noqa: BLE001 # pylint: disable=broad-exception-caught
            artifact.reference_checks.append(
                {"case_id": uid, "passed": False, "error": str(error)}
            )
            artifact.failures.append(f"Independent SMT control error: {uid}: {error}")
    return scripts


def _prepare_cell(
    plan: ExperimentPlan, cell: ExperimentCell, root: Path
) -> tuple[CellPreparation, list[LogicTestCase]]:
    artifact = CellPreparation(cell=cell)
    dataset: list[LogicTestCase] = []
    try:
        dataset = generate_cell(plan, cell)
        relative_dir = Path("cells") / cell.cell_id
        storage = FileStorageManager(root / relative_dir)
        dataset_path = storage.save_dataset("dataset_controlled.jsonl", dataset)
        artifact.dataset_path = dataset_path.relative_to(root).as_posix()
        artifact.dataset_sha256 = compute_file_sha256(dataset_path)
        serialized = _read_serialized(dataset_path)
        scripts = _verify_cell(dataset, artifact, serialized)
        expected = _expected_cases(plan, cell)
        artifact.smt_passed = _smt_evidence(artifact.smt_checks, expected, cell.k)
        artifact.reference_passed = _reference_evidence(
            artifact.reference_checks, expected
        )
        dataset = [LogicTestCase.model_validate(row) for row in serialized]
        reference_path = root / relative_dir / "reference_smt.json"
        reference_path.write_text(
            json.dumps(scripts, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        artifact.reference_path = reference_path.relative_to(root).as_posix()
        artifact.reference_sha256 = compute_file_sha256(reference_path)
        artifact.leakage_report = calculate_leakage(dataset, [cell.k])
        artifact.leakage_acceptance = _accept(artifact.leakage_report, plan, [cell.k])
        # Pylint sees inherited Pydantic defaults as FieldInfo rather than lists.
        artifact.failures.extend(artifact.leakage_acceptance.failures)  # pylint: disable=no-member
    except Exception as error:  # noqa: BLE001 # pylint: disable=broad-exception-caught
        artifact.failures.append(  # pylint: disable=no-member
            f"Cell preparation error: {type(error).__name__}: {error}"
        )
    return artifact, dataset


def _audit_evidence(
    report: LeakageReport, plan: ExperimentPlan, cells: list[ExperimentCell]
) -> bool:
    topologies = {(cell.pattern_id, cell.k) for cell in cells}
    ks = sorted({k for _, k in topologies})
    if not _accept(report, plan, ks).passed:
        return False
    families_per_topology = len(plan.seeds) * plan.pairs_per_seed
    family_counts = {
        "global": len(topologies) * families_per_topology,
        **{
            f"mus_size={k}": sum(size == k for _, size in topologies)
            * families_per_topology
            for k in ks
        },
    }
    primary = {
        "global": {"word_tfidf": report.global_word, "char_tfidf": report.global_char},
        **report.by_mus_size,
    }
    return all(
        count >= 2 and view[group][analyzer].n_splits == min(5, count)
        for view in [primary, *report.by_input.values()]
        for group, count in family_counts.items()
        for analyzer in ("word_tfidf", "char_tfidf")
    )


def _cell_checks_passed(item: CellPreparation, plan: ExperimentPlan) -> bool:
    expected = _expected_cases(plan, item.cell)
    checks = (
        not item.failures,
        item.smt_passed,
        item.reference_passed,
        bool(item.dataset_path),
        bool(item.reference_path),
        _smt_evidence(item.smt_checks, expected, item.cell.k),
        _reference_evidence(item.reference_checks, expected),
    )
    if (
        not all(checks)
        or item.leakage_report is None
        or item.leakage_acceptance is None
    ):
        return False
    return (
        item.leakage_acceptance.passed
        and item.leakage_acceptance.threshold == plan.leakage_threshold
        and item.leakage_acceptance.cv_grouping == "family_id"
        and _audit_evidence(item.leakage_report, plan, [item.cell])
    )


def manifest_checks_passed(manifest: ExperimentManifest, plan: ExperimentPlan) -> bool:
    """Recompute required verdicts, including measured audit scores, on loading."""
    if (
        manifest.plan_sha256 != plan.plan_hash
        or manifest.manifest_version != plan.protocol_version
    ):
        return False
    if (
        manifest.cv_grouping != "family_id"
        or manifest.failures
        or [item.cell for item in manifest.cells] != plan.cells()
    ):
        return False
    if not all(_cell_checks_passed(item, plan) for item in manifest.cells):
        return False
    return bool(
        manifest.combined_path
        and manifest.combined_sha256
        and manifest.combined_leakage is not None
        and manifest.combined_acceptance is not None
        and manifest.combined_acceptance.passed
        and manifest.combined_acceptance.cv_grouping == "family_id"
        and manifest.combined_acceptance.threshold == plan.leakage_threshold
        and _audit_evidence(manifest.combined_leakage, plan, plan.cells())
    )


def prepare_experiment(plan: ExperimentPlan, output_dir: Path) -> ExperimentManifest:
    """One attempt at every prevalidated cell. No retries or sample/seed tuning."""
    plan = ExperimentPlan.model_validate(plan.model_dump())
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    manifest = ExperimentManifest(
        manifest_version=plan.protocol_version,
        plan=plan.normalized(),
        plan_sha256=plan.plan_hash,
        source_bundle_sha256=compute_source_bundle_hash(),
        environment={
            "python": platform.python_version(),
            "z3": z3.get_version_string(),
            "numpy": np.__version__,
            "scikit_learn": sklearn.__version__,
        },
        cells=[],
    )
    combined = []
    for cell in plan.cells():
        artifact, dataset = _prepare_cell(plan, cell, root)
        manifest.cells.append(artifact)
        combined.extend(dataset)
    if combined:
        try:
            path = FileStorageManager(root).save_dataset(
                "combined_controlled.jsonl", combined
            )
            manifest.combined_path = path.name
            manifest.combined_sha256 = compute_file_sha256(path)
            if _read_serialized(path) != [
                json.loads(case.model_dump_json()) for case in combined
            ]:
                raise ValueError(
                    "combined serialized dataset differs from verified cell content"
                )
            ks = sorted({cell.k for cell in plan.cells()})
            manifest.combined_leakage = calculate_leakage(combined, ks)
            manifest.combined_acceptance = _accept(manifest.combined_leakage, plan, ks)
        except Exception as error:  # noqa: BLE001 # pylint: disable=broad-exception-caught
            manifest.failures.append(  # pylint: disable=no-member
                f"Combined audit error: {type(error).__name__}: {error}"
            )
    manifest.ready_for_evaluation = manifest_checks_passed(manifest, plan)
    (root / SERIES_MANIFEST).write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return manifest
