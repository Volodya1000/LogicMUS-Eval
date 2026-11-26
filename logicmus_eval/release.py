"""Require an accepted, matching manifest before evaluating newly generated v2 data."""

import json
from pathlib import Path

from logicmus_eval.enums import ManifestFilename
from logicmus_eval.hashing import compute_file_sha256
from logicmus_eval.models.manifests import BenchmarkManifest
from logicmus_eval.models.pipeline import LeakageReport


def assert_dataset_approved(dataset_path: Path) -> None:
    """Legacy/external datasets remain readable; v2 requires its release audit."""
    if dataset_path.name != ManifestFilename.DATASET_JSONL.value:
        is_v2 = False
        with dataset_path.open(encoding="utf-8") as stream:
            for line in stream:
                if (
                    line.strip()
                    and json.loads(line).get("metadata", {}).get("generator_version")
                    == 2
                ):
                    is_v2 = True
                    break
        if not is_v2:
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
