"""Require an accepted, matching manifest before evaluating newly generated v2 data."""

import json
from pathlib import Path

from logicmus_eval.enums import ManifestFilename
from logicmus_eval.hashing import compute_file_sha256
from logicmus_eval.models.manifests import BenchmarkManifest
from logicmus_eval.models.pipeline import LeakageReport


def _assert_controlled_approved(dataset_path: Path) -> None:  # pylint: disable=too-many-locals
    # Local import keeps the legacy release contract independent of preparation.
    from logicmus_eval.experiment_plan import (  # pylint: disable=import-outside-toplevel
        ExperimentPlan,
    )
    from logicmus_eval.experiment_preparation import (  # pylint: disable=import-outside-toplevel
        SERIES_MANIFEST,
        ExperimentManifest,
        manifest_checks_passed,
    )

    candidates = [
        parent / SERIES_MANIFEST for parent in list(dataset_path.resolve().parents)[:3]
    ]
    manifest_path = next((p for p in candidates if p.is_file()), None)
    if manifest_path is None:
        raise ValueError("Dataset not approved: controlled series manifest is missing")
    manifest = ExperimentManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    plan = ExperimentPlan.model_validate(manifest.plan)
    if not manifest.ready_for_evaluation or not manifest_checks_passed(manifest, plan):
        raise ValueError(
            "Dataset not approved: controlled series has failed mandatory checks"
        )
    root = manifest_path.parent.resolve()
    artifacts = [(manifest.combined_path, manifest.combined_sha256)]
    for item in manifest.cells:
        artifacts.extend(
            (
                (item.dataset_path, item.dataset_sha256),
                (item.reference_path, item.reference_sha256),
            )
        )
    registered = False
    for relative, expected_hash in artifacts:
        if relative is None or expected_hash is None:
            raise ValueError("Dataset not approved: incomplete series artifacts")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Dataset not approved: missing or invalid series artifact")
        if compute_file_sha256(path) != expected_hash:
            raise ValueError(
                "Dataset not approved: series artifact hash differs from manifest"
            )
        registered = registered or path == dataset_path.resolve()
    if not registered:
        raise ValueError(
            "Dataset not approved: dataset is not registered in series manifest"
        )


def assert_dataset_approved(dataset_path: Path) -> None:
    """Legacy/external datasets remain readable; v2 requires its release audit."""
    canonical = dataset_path.name in {
        "dataset_controlled.jsonl",
        "combined_controlled.jsonl",
    }
    controlled_location = any(
        (parent / "series.manifest.json").is_file()
        for parent in list(dataset_path.resolve().parents)[:3]
    )
    if canonical or controlled_location:
        _assert_controlled_approved(dataset_path)
        return
    is_v2 = False
    with dataset_path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            metadata = json.loads(line).get("metadata", {})
            is_v2 = is_v2 or metadata.get("generator_version") == 2
            if any(
                str(metadata.get(key, "")).startswith("controlled-")
                for key in ("protocol_version", "generator_version")
            ):
                _assert_controlled_approved(dataset_path)
                return
    if dataset_path.name != ManifestFilename.DATASET_JSONL.value and not is_v2:
        return
    manifest_path = dataset_path.with_suffix(".manifest.json")
    if not manifest_path.exists():
        manifest_path = dataset_path.parent / ManifestFilename.MANIFEST_JSON.value
    if not manifest_path.exists():
        raise ValueError("Dataset not approved: v2 manifest is missing")
    manifest = BenchmarkManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    audit = manifest.leakage_acceptance
    if audit is None or not audit.passed:
        raise ValueError("Dataset not approved: leakage audit failed or is unavailable")
    if manifest.artifacts.dataset_sha256 != compute_file_sha256(dataset_path):
        raise ValueError("Dataset not approved: dataset hash differs from its manifest")
    # Validate the actual stored diagnostic scores as well as the summary flag.
    report = LeakageReport(
        global_word=manifest.leakage_metrics_global.word_tfidf,
        global_char=manifest.leakage_metrics_global.char_tfidf,
        by_mus_size=manifest.leakage_metrics_by_mus_size,
        by_input=manifest.leakage_metrics_by_input,
    )
    if not report.acceptance(
        audit.threshold, manifest.parameters.mus_sizes, ("direct", "z3")
    ).passed:
        raise ValueError(
            "Dataset not approved: diagnostic scores contradict acceptance"
        )
