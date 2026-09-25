import hashlib
from pathlib import Path


def compute_file_sha256(file_path: Path) -> str:
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def compute_source_hash(files: list[Path]) -> str:
    hasher = hashlib.sha256()
    for sf in files:
        if sf.exists():
            hasher.update(sf.read_bytes())
    return hasher.hexdigest()
