"""Stop legacy consumers before their historical joins or metric reconstruction."""

import csv
from collections.abc import Mapping
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

JSON_OBJECT = TypeAdapter(dict[str, JsonValue])
JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)

MESSAGE = (
    "Controlled results require: logicmus-eval analyze-controlled "
    "--run RUN --plan PLAN.json --output OUT"
)


def reject_report(data: Mapping[str, JsonValue]) -> None:
    details = data.get("details")
    if data.get("runner_provenance") or (
        isinstance(details, list)
        and any(isinstance(item, dict) and item.get("experiment") for item in details)
    ):
        raise ValueError(MESSAGE)


def reject_controlled(root: Path) -> None:
    if any(
        (directory / name).exists()
        for directory in (root, root.parent)
        for name in ("run.manifest.json", "analysis.manifest.json")
    ):
        raise ValueError(MESSAGE)
    for name in ("summary.csv", "details.csv", "cases.csv"):
        path = root / name
        if path.is_file():
            with path.open(encoding="utf-8", newline="") as stream:
                fields = next(csv.reader(stream), [])
            if {
                "case_uid",
                "family_id",
                "runner_provenance",
                "series_kind",
            }.intersection(fields):
                raise ValueError(MESSAGE)
    manifest = root / "manifest.json"
    if manifest.is_file():
        items = JSON_VALUE.validate_json(manifest.read_bytes())
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and isinstance(
                    report_name := item.get("report"), str
                ):
                    report = Path(report_name)
                    if not report.is_file():
                        report = root / report
                    if report.is_file():
                        reject_report(JSON_OBJECT.validate_json(report.read_bytes()))
