"""Portable release-local paths and JSON objects."""

import json
from pathlib import Path
from typing import Any

from logicmus_eval.hashing import compute_file_sha256


def local(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError(f"Artifact must be relative and inside release: {relative}")
    return path


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path.name}")  # noqa: TRY004
    return payload


def admission_files(root: Path) -> dict[str, str]:
    return {
        name: compute_file_sha256(root / name)
        for name in (
            "release.manifest.json",
            "preparation.json",
            "backend.evidence.json",
            "smoke.evidence.json",
            "bundle/binding/binding.json",
            "bundle/binding/analysis.bound.json",
        )
    }


def check_admission(root: Path) -> None:
    admission = read_json(root / "admission.json")
    if (
        admission["files"] != admission_files(root)
        or admission["before_first_http"] is not True
    ):
        raise ValueError("Release admission changed")
