"""Offline resume identity checking under the run's writer lock."""

import json
from pathlib import Path
from typing import Any

from logicmus_eval.runner.config import RunConfig
from logicmus_eval.runner.preflight import Preflight, digest, preflight


def resume_preflight(
    root: Path, config: RunConfig | None = None
) -> tuple[dict[str, Any], Preflight]:
    manifest = json.loads((root / "run.manifest.json").read_text(encoding="utf-8"))
    if manifest.get("manifest_sha256") != digest(manifest.get("payload")):
        raise ValueError("Run manifest is corrupt")
    payload = manifest["payload"]
    saved = RunConfig.model_validate(payload["identity"]["config"])
    ready = preflight(config or saved)
    if ready.identity != payload["identity"]:
        raise ValueError(
            "Incompatible resume: configuration, series, requests, source or protocol differs"
        )
    if payload["job_ids"] != [job.job_id for job in ready.jobs]:
        raise ValueError("Incompatible resume: planned inventory differs")
    return manifest, ready
