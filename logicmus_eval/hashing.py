import hashlib
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent


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
    if files is not None:
        return compute_source_hash(files)
    hasher = hashlib.sha256()
    sources = sorted(SOURCE_ROOT.rglob("*.py"))
    if not sources:
        raise RuntimeError("Source bundle is empty")
    for source in sources:
        hasher.update(
            source.relative_to(SOURCE_ROOT).as_posix().encode("utf-8") + b"\0"
        )
        _update_hash_from_file(hasher, source)
    return hasher.hexdigest()
