import hashlib
from pathlib import Path

SOURCE_BUNDLE_FILES: list[Path] = [
    Path("src/models/rules.py"),
    Path("src/models/test_case.py"),
    Path("src/models/manifests.py"),
    Path("src/models/pipeline.py"),
    Path("src/models/llm.py"),
    Path("src/templates.py"),
    Path("src/generator.py"),
    Path("src/verifier.py"),
    Path("src/extractor.py"),
    Path("src/run_pipeline.py"),
    Path("src/storage.py"),
    Path("src/hashing.py"),
]


def _update_hash_from_file(hasher: "hashlib._Hash", file_path: Path) -> None:
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)


def compute_file_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    _update_hash_from_file(hasher, file_path)
    return hasher.hexdigest()


def compute_source_hash(files: list[Path]) -> str:
    hasher = hashlib.sha256()
    for sf in files:
        if sf.exists():
            _update_hash_from_file(hasher, sf)
    return hasher.hexdigest()


def compute_source_bundle_hash(files: list[Path] | None = None) -> str:
    return compute_source_hash(files if files is not None else SOURCE_BUNDLE_FILES)
