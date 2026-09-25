from pathlib import Path

from src.enums import TemplatePackId
from src.models.manifests import (
    ArtifactsManifest,
    BenchmarkManifest,
    EnvironmentManifest,
    LeakageMetricsGlobal,
    ParametersManifest,
    TfidfMetrics,
    ValidationResultsManifest,
)
from src.models.test_case import LogicTestCase


class FakeStorageManager:
    def __init__(self):
        self.saved_datasets = {}
        self.saved_manifests = {}

    def save_dataset(self, filename: str, dataset: list[LogicTestCase]) -> Path:
        self.saved_datasets[filename] = dataset
        return Path(f"/fake/dir/{filename}")

    def save_manifest(self, filename: str, manifest: BenchmarkManifest) -> Path:
        self.saved_manifests[filename] = manifest
        return Path(f"/fake/dir/{filename}")


def test_fake_storage_saves_dataset_behavior():
    storage = FakeStorageManager()
    case = LogicTestCase(
        case_id="mus1_SAT",
        mus_size=1,
        is_satisfiable=True,
        template_pack_id=TemplatePackId.PACK_00,
        predicate_mapping={"A": "P"},
        rules=[],
        mus_expected=[],
    )

    filepath = storage.save_dataset("test.jsonl", [case])
    assert filepath.name == "test.jsonl"
    assert "test.jsonl" in storage.saved_datasets
    assert storage.saved_datasets["test.jsonl"][0].case_id == "mus1_SAT"


def test_fake_storage_saves_manifest_behavior():
    storage = FakeStorageManager()

    empty_metrics = TfidfMetrics(mean_f1=0.0, std_f1=0.0)
    manifest = BenchmarkManifest(
        artifacts=ArtifactsManifest(
            dataset_filename="", dataset_sha256="", source_bundle_sha256=""
        ),
        environment=EnvironmentManifest(python="", z3="", numpy="", scikit_learn=""),
        parameters=ParametersManifest(
            mus_sizes=[],
            pairs_per_group=0,
            total_cases=0,
            rules_per_case=0,
            base_seed=0,
        ),
        validation_results=ValidationResultsManifest(
            sat_correctness="0/0",
            unsat_correctness="0/0",
            mus_validity="0/0",
            mus_minimality="0/0",
        ),
        leakage_metrics_global=LeakageMetricsGlobal(
            word_tfidf=empty_metrics, char_tfidf=empty_metrics
        ),
        leakage_metrics_by_mus_size={},
    )

    filepath = storage.save_manifest("manifest.json", manifest)
    assert filepath.name == "manifest.json"
    assert "manifest.json" in storage.saved_manifests
    assert storage.saved_manifests["manifest.json"] == manifest
