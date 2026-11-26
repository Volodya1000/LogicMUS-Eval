import hashlib
import json

import pytest

from logicmus_eval.enums import ManifestFilename
from logicmus_eval.hashing import compute_source_bundle_hash
from logicmus_eval.run_pipeline import GenerationConfig, run_generation


def test_rejected_small_sample_persists_honest_diagnostics(tmp_path):
    with pytest.raises(ValueError, match="Leakage audit failed"):
        run_generation(GenerationConfig([2], 1, 5, 42, str(tmp_path)))
    manifest = json.loads((tmp_path / ManifestFilename.MANIFEST_JSON.value).read_text())
    assert manifest["parameters"]["generator_version"] == 2
    assert manifest["leakage_acceptance"]["passed"] is False
    assert (
        manifest["leakage_metrics_global"]["word_tfidf"]["mean_balanced_accuracy"]
        is None
    )
    assert (
        manifest["artifacts"]["source_bundle_sha256"] != hashlib.sha256(b"").hexdigest()
    )
    assert not (tmp_path / "dataset_v1_frozen.jsonl").exists()


def test_source_bundle_hash_is_nonempty_and_independent_of_cwd(tmp_path, monkeypatch):
    before = compute_source_bundle_hash()
    monkeypatch.chdir(tmp_path)
    assert compute_source_bundle_hash() == before
    assert before != hashlib.sha256(b"").hexdigest()


def test_published_v1_can_still_be_found():
    from pathlib import Path

    from logicmus_eval.evaluate_llm import _resolve_dataset_filename

    root = Path(__file__).resolve().parents[2]
    assert (
        _resolve_dataset_filename(str(root / "datasets/v1.0"))
        == "dataset_v1_frozen.jsonl"
    )


def test_rejected_dataset_cannot_reach_model_inference(tmp_path, monkeypatch):
    from logicmus_eval import evaluate_llm

    with pytest.raises(ValueError, match="Leakage audit failed"):
        run_generation(GenerationConfig([2], 1, 5, 42, str(tmp_path)))

    def forbidden_extractor(*_args, **_kwargs):
        raise AssertionError("Rejected data reached model construction")

    monkeypatch.setattr(evaluate_llm, "StructuredOutputExtractor", forbidden_extractor)
    with pytest.raises(ValueError, match="not approved"):
        evaluate_llm.run_evaluation(str(tmp_path), "unused", "direct", 2, "report.json")


def test_renamed_rejected_v2_is_still_rejected(tmp_path):
    from logicmus_eval.release import assert_dataset_approved

    with pytest.raises(ValueError, match="Leakage audit failed"):
        run_generation(GenerationConfig([2], 1, 5, 42, str(tmp_path)))
    alias = tmp_path / "renamed.jsonl"
    alias.write_bytes((tmp_path / ManifestFilename.DATASET_JSONL.value).read_bytes())
    with pytest.raises(ValueError, match="not approved"):
        assert_dataset_approved(alias)


@pytest.mark.parametrize("missing", ["all", "analyzers"])
def test_release_requires_all_expected_k_measurements(tmp_path, missing):
    from logicmus_eval.release import assert_dataset_approved

    run_generation(GenerationConfig([2], 4, 5, 42, str(tmp_path), 1.0))
    path = tmp_path / ManifestFilename.MANIFEST_JSON.value
    manifest = json.loads(path.read_text())
    manifest["leakage_metrics_by_mus_size"] = (
        {} if missing == "all" else {"mus_size=2": {}}
    )
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="not approved"):
        assert_dataset_approved(tmp_path / ManifestFilename.DATASET_JSONL.value)


def test_frozen_v1_is_preferred_to_unrelated_jsonl(tmp_path):
    from logicmus_eval.evaluate_llm import _resolve_dataset_filename

    (tmp_path / "archive.jsonl").write_text("{}\n")
    (tmp_path / "dataset_v1_frozen.jsonl").write_text("{}\n")
    assert _resolve_dataset_filename(str(tmp_path)) == "dataset_v1_frozen.jsonl"
