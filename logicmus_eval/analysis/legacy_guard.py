"""Stop legacy consumers before their historical joins or metric reconstruction."""

import csv
import json
from pathlib import Path
from typing import Any

MESSAGE = (
    "Controlled results require: logicmus-eval analyze-controlled "
    "--run RUN --plan PLAN.json --output OUT"
)


def reject_report(data: dict[str, Any]) -> None:
    if data.get("runner_provenance") or any(
        item.get("experiment") for item in data.get("details", [])
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
        items = json.loads(manifest.read_text(encoding="utf-8"))
        if isinstance(items, list):
            for item in items:
                if isinstance(item, dict) and item.get("report"):
                    report = Path(item["report"])
                    if not report.is_file():
                        report = root / report
                    if report.is_file():
                        reject_report(json.loads(report.read_text(encoding="utf-8")))
