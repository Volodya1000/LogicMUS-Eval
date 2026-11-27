# CLI imports are deferred until pytest fixture setup because smoke CLI modules
# register signal handlers at import time.
# pylint: disable=import-outside-toplevel

import json
from pathlib import Path

import pytest

from logicmus_eval.enums import ManifestFilename
from logicmus_eval.run_pipeline import GenerationConfig, run_generation


def test_smoke_grid_uses_the_generated_versioned_file(tmp_path, monkeypatch):
    from scripts import run_smoke_grid as smoke

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        smoke,
        "GRID",
        [{"exp": "test", "name": "tiny", "mus_size": 2, "total_rules": 5}],
    )
    monkeypatch.setattr(smoke, "MODELS", ["unused"])
    monkeypatch.setattr(smoke, "STRATEGIES", ["direct"])

    def accepted_generation(config):
        run_generation(
            GenerationConfig(
                config.mus_sizes,
                4,
                config.total_rules,
                config.base_seed,
                config.output_dir,
                1.0,
            )
        )

    monkeypatch.setattr(smoke, "run_generation", accepted_generation)

    def offline_report(dataset_dir, **_kwargs):
        from types import SimpleNamespace

        from logicmus_eval.evaluation.pipeline import EvaluationPipeline
        from logicmus_eval.models.evaluation import CasePrediction, ExtractionMetadata
        from logicmus_eval.storage import FileStorageManager

        assert (Path(dataset_dir) / ManifestFilename.DATASET_JSONL.value).exists()
        pipeline = EvaluationPipeline(
            strategy=SimpleNamespace(
                evaluate_case=lambda *_args: (
                    CasePrediction(is_sat=True),
                    ExtractionMetadata(),
                )
            ),
            extractor=SimpleNamespace(),
            metrics=[],
        )
        pipeline.run(
            FileStorageManager(dataset_dir).load_dataset(
                ManifestFilename.DATASET_JSONL.value
            ),
            output_path=Path(dataset_dir) / _kwargs["output_file"],
        )

    monkeypatch.setattr(smoke, "run_evaluation", offline_report)
    smoke.main()
    manifests = list(tmp_path.glob("experiments/*/manifest.json"))
    assert len(manifests) == 1
    assert json.loads(manifests[0].read_text())[0]["dataset_sha256"]


def test_full_grid_rechecks_a_cached_rejected_dataset(tmp_path):
    from scripts.run_full_grid import GridConfig, generate_dataset

    with pytest.raises(ValueError, match="Leakage audit failed"):
        run_generation(GenerationConfig([2], 1, 5, 42, str(tmp_path)))
    with pytest.raises(ValueError, match="not approved"):
        generate_dataset(GridConfig("test", "tiny", 2, 5, 1, 42), tmp_path)


def test_full_grid_does_not_load_models_without_approved_data(tmp_path, monkeypatch):
    import sys

    from scripts import run_full_grid as full

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["run_full_grid.py", "--pairs", "1"])
    monkeypatch.setattr(
        full,
        "build_grid",
        lambda _pairs: [full.GridConfig("test", "tiny", 2, 5, 1, 42)],
    )

    def rejected_generation(*_args, **_kwargs):
        raise ValueError("Rejected dataset")

    def forbidden_load(*_args, **_kwargs):
        raise AssertionError("Model load must not happen without approved data")

    monkeypatch.setattr(full, "run_generation", rejected_generation)
    monkeypatch.setattr(full, "load_model", forbidden_load)
    monkeypatch.setattr(full, "unload_all", lambda *_args: None)
    monkeypatch.setattr(full, "show_loaded_models", lambda *_args: "")
    with pytest.raises(RuntimeError, match="No approved datasets"):
        full.main()
