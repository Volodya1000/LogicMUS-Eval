"""Audit saved JSONL or one explicit plan cell offline; never prepares a release."""

import argparse
import json
from pathlib import Path

from logicmus_eval.controlled_generation import generate_cell
from logicmus_eval.duplicate_cues import audit_duplicates
from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.hashing import compute_file_sha256
from logicmus_eval.models.test_case import LogicTestCase


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--dataset", type=Path)
    source.add_argument("--plan", type=Path)
    parser.add_argument("--pattern", default="idem")
    parser.add_argument("--n", type=int, default=16)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.plan:
        plan = ExperimentPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
        cells = [
            c for c in plan.cells() if c.pattern_id == args.pattern and c.n == args.n
        ]
        if len(cells) != 1:
            parser.error("Select exactly one plan cell with --pattern and --n")
        cases = generate_cell(plan, cells[0])
        provenance = {
            "plan_sha256": plan.plan_hash,
            "cell": cells[0].model_dump(mode="json"),
        }
    else:
        cases = [
            LogicTestCase.model_validate_json(line)
            for line in args.dataset.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        provenance = {"dataset_sha256": compute_file_sha256(args.dataset)}
    payload = {
        "audit_version": "duplicate-cues-v1",
        "protocol_versions": sorted(
            {str(c.metadata.get("protocol_version")) for c in cases}
        ),
        "provenance": provenance,
        "baselines": {
            name: value.model_dump(mode="json")
            for name, value in audit_duplicates(cases).items()
        },
        "limitation": (
            "These fixed cues do not measure all leakage and do not explain TF-IDF scores."
        ),
    }
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
