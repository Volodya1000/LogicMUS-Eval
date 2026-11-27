"""Explicit descriptive reading of unattested historical JSON/CSV formats."""

import csv
import hashlib
import io
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from logicmus_eval.analysis.artifacts import write_csv
from logicmus_eval.analysis.models import AnalysisManifest, LegacyEvidence

LEGACY_ROWS: TypeAdapter[list[dict[str, JsonValue]] | dict[str, JsonValue]] = (
    TypeAdapter(list[dict[str, JsonValue]] | dict[str, JsonValue])
)


def describe(inputs: list[Path], output: Path, manifest: AnalysisManifest) -> None:
    rows: list[dict[str, JsonValue]] = []
    for path in inputs:
        if not path.is_file():
            raise ValueError("Legacy mode takes explicit JSON/CSV files")
        # Read and hash exactly the same bytes, even for legacy descriptions.
        raw = path.read_bytes()
        manifest.inputs.append(
            LegacyEvidence(
                path=str(path.resolve()), sha256=hashlib.sha256(raw).hexdigest()
            )
        )
        if path.suffix.lower() == ".csv":
            records = LEGACY_ROWS.validate_python(
                list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
            )
        else:
            records = LEGACY_ROWS.validate_json(raw)
        if isinstance(records, dict):
            records = [records]
        for item in records:
            if item.get("runner_provenance") or item.get("analysis_version"):
                raise ValueError(
                    "Controlled data requires primary/diagnostic verification"
                )
            rows.append(
                {
                    **item,
                    "source": str(path.resolve()),
                    "provenance_status": "legacy",
                    "inference_status": "descriptive-only; no provenance or pairing guarantees",
                }
            )
    write_csv(output / "legacy.csv", rows, ["source", "provenance_status"])
