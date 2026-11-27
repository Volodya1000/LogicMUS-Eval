"""Verified historical snapshots, independent of current checkout and endpoints."""
# pylint: disable=too-many-locals

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from logicmus_eval.evaluation.reports import verify_runner_report
from logicmus_eval.hashing import compute_file_sha256
from logicmus_eval.models.evaluation import EvaluationSummary
from logicmus_eval.runner.journal import RunJournal
from logicmus_eval.runner.preflight import digest


@dataclass
class Snapshot:
    root: Path
    payload: dict[str, Any]
    report: EvaluationSummary
    requests: dict[str, dict[str, Any]]
    evidence: dict[str, Any]


def discover(inputs: list[Path]) -> list[Path]:
    reports = set()
    for supplied in inputs:
        path = supplied.resolve()
        if path.is_file():
            reports.add(path)
        elif (path / "run.manifest.json").is_file():
            reports.add(path / "report.json")
        else:
            found = sorted(path.rglob("run.manifest.json"))
            if not found:
                raise ValueError(f"No saved runner manifests in {path}")
            reports.update(item.parent / "report.json" for item in found)
    if not reports:
        raise ValueError("No input reports")
    return sorted(reports)


def load_snapshots(inputs: list[Path]) -> list[Snapshot]:
    by_run: dict[str, Snapshot] = {}
    for path in discover(inputs):
        # Even an explicitly supplied stale subgroup must be rejected.
        report = verify_runner_report(path)
        root = next(
            p
            for p in (path.parent, path.parent.parent)
            if (p / "run.manifest.json").is_file()
        )
        root_report = root / "report.json"
        if path != root_report:
            report = verify_runner_report(root_report)
        manifest = json.loads((root / "run.manifest.json").read_text(encoding="utf-8"))
        payload = manifest["payload"]
        assert report.runner_provenance is not None
        with RunJournal(root, manifest["manifest_sha256"], read_only=True) as journal:
            if journal.head != report.runner_provenance["journal_head_sha256"]:
                raise ValueError(
                    "Journal changed during analysis; use a quiescent snapshot"
                )
            requests = {
                event["job_id"]: event["request"]
                for event in journal.events
                if event["kind"] == "started"
            }
            evidence = {
                "run_id": payload["run_id"],
                "root": str(root),
                "manifest_sha256": manifest["manifest_sha256"],
                "identity_sha256": digest(payload["identity"]),
                "journal_head_sha256": journal.head,
                "journal_event_count": len(journal.events),
                "files": {
                    str(p.relative_to(root)): compute_file_sha256(p)
                    for p in [
                        root / "run.manifest.json",
                        root / "journal.sqlite3",
                        root_report,
                    ]
                },
            }
        run_id = payload["run_id"]
        if run_id in by_run:
            previous = by_run[run_id]
            if any(
                previous.evidence[key] != evidence[key]
                for key in (
                    "manifest_sha256",
                    "journal_head_sha256",
                    "journal_event_count",
                )
            ):
                raise ValueError(
                    f"Conflicting snapshots for run_id {run_id}; select one explicitly"
                )
            previous.evidence.setdefault("supplied_reports", []).append(
                {"path": str(path), "sha256": compute_file_sha256(path)}
            )
        else:
            evidence["supplied_reports"] = [
                {"path": str(path), "sha256": compute_file_sha256(path)}
            ]
            by_run[run_id] = Snapshot(root, payload, report, requests, evidence)
    return [snapshot for _, snapshot in sorted(by_run.items())]


def conditions(snapshot: Snapshot, model_id: str, strategy: str) -> dict[str, Any]:
    """Common execution and model conditions, with strategy-scoped Z3 fields.

    Prompt/schema signatures are checked separately per strategy. Actual case
    prompts are checked by case_uid, never compared across direct and Z3.
    """
    identity = snapshot.payload["identity"]
    config = identity["config"]
    model = next(item for item in config["models"] if item["model_id"] == model_id)
    return {
        **{
            key: identity.get(key)
            for key in (
                "runner_protocol",
                "transport_protocol",
                "metric_definitions_version",
                "report_schema_version",
                "source_bundle_sha256",
                "runtime",
            )
        },
        "model": model,
        **{
            key: config.get(key)
            for key in ("endpoint", "request_timeout_seconds", "retry")
        },
        **(
            {
                "z3_execution_protocol_version": identity.get(
                    "z3_execution_protocol_version"
                ),
                "z3_timeout_seconds": config["z3_timeout_seconds"],
            }
            if strategy == "z3"
            else {}
        ),
    }


def check_compatibility(rows: list[dict[str, Any]]) -> dict[str, Any]:
    common: dict[Any, str] = {}
    scoped: dict[Any, str] = {}
    schemas: dict[str, str] = {}
    requests: dict[tuple[str, str, str], str] = {}
    profiles: dict[tuple[str, str], Any] = {}
    for row in rows:
        snapshot: Snapshot = row["snapshot"]
        model, strategy = row["model_id"], row["strategy"]
        condition = conditions(snapshot, model, strategy)
        if condition["metric_definitions_version"] != "3":
            raise ValueError(
                "Unsupported historical metric definitions; use legacy mode"
            )
        shared = {
            key: value for key, value in condition.items() if not key.startswith("z3_")
        }
        checks = [
            (common, model, digest(shared)),
            (scoped, (model, strategy), digest(condition)),
        ]
        for registry, key, fingerprint in checks:
            if key in registry and registry[key] != fingerprint:
                raise ValueError(
                    f"Incompatible execution/transport/inference conditions for {key}"
                )
            registry[key] = fingerprint
        request = snapshot.requests[row["job_id"]]
        body = request["body"]
        signature = digest(
            {key: value for key, value in body.items() if key != "messages"}
        )
        schema_key = model + "/" + strategy
        if schema_key in schemas and schemas[schema_key] != signature:
            raise ValueError(f"Incompatible prompt/schema/parameters for {schema_key}")
        schemas[schema_key] = signature
        request_key = (model, strategy, row["case_uid"])
        fingerprint = digest(request)
        if request_key in requests and requests[request_key] != fingerprint:
            raise ValueError(f"Incompatible saved prompts for {request_key}")
        requests[request_key] = fingerprint
        trace = row["outcome"].inference or {}
        profile = trace.get("model_profile") or {}
        observed = profile.get("observed", {})
        for field, value in observed.items():
            if value is None:
                continue
            profile_key = (model, field)
            if profile_key in profiles and profiles[profile_key] != value:
                raise ValueError(f"Incompatible observed model profile {profile_key}")
            profiles[profile_key] = value
    return {
        "status": "compatible",
        "common_conditions": common,
        "strategy_conditions": {str(key): value for key, value in scoped.items()},
        "schema_parameter_hashes": schemas,
        "unknowns": [
            "Unobserved model facts and backend-applied settings remain unverified."
        ],
    }
