import hashlib
import tempfile
from pathlib import Path

from src.hashing import compute_file_sha256, compute_source_hash


def test_compute_file_sha256():
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"hello world")
        tmp_path = Path(tmp.name)

    try:
        expected_hash = hashlib.sha256(b"hello world").hexdigest()
        assert compute_file_sha256(tmp_path) == expected_hash
    finally:
        tmp_path.unlink()


def test_compute_source_hash():
    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_path = Path(tmp_dir)
        file1 = dir_path / "f1.txt"
        file2 = dir_path / "f2.txt"

        file1.write_bytes(b"A")
        file2.write_bytes(b"B")

        expected_hash = hashlib.sha256(b"AB").hexdigest()
        assert compute_source_hash([file1, file2]) == expected_hash


def test_compute_source_hash_ignores_missing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_path = Path(tmp_dir)
        file1 = dir_path / "f1.txt"
        missing_file = dir_path / "missing.txt"

        file1.write_bytes(b"A")

        result_with_missing = compute_source_hash([file1, missing_file])
        result_without_missing = compute_source_hash([file1])

        assert result_with_missing == result_without_missing