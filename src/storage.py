import json
from pathlib import Path
from typing import Protocol

from src.models.manifests import BenchmarkManifest
from src.models.test_case import LogicTestCase


class StorageProtocol(Protocol):
    def save_dataset(self, filename: str, dataset: list[LogicTestCase]) -> Path: ...

    def save_manifest(self, filename: str, manifest: BenchmarkManifest) -> Path: ...


class FileStorageManager:
    def __init__(self, output_dir: str | Path) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_dataset(self, filename: str, dataset: list[LogicTestCase]) -> Path:
        output_path = self.output_dir / filename
        with open(output_path, "w", encoding="utf-8") as f:
            f.writelines(
                json.dumps(case.to_dict(), ensure_ascii=False) + "\n"
                for case in dataset
            )
        return output_path

    def save_manifest(self, filename: str, manifest: BenchmarkManifest) -> Path:
        manifest_path = self.output_dir / filename
        with open(manifest_path, "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))
        return manifest_path
