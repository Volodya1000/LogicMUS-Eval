"""Synthetic external measurements test selection plumbing, never real accounting."""

# Imported fixtures retain pytest's fixture names.
# pylint: disable=redefined-outer-name,unused-argument,too-many-locals

import hashlib
import json
from pathlib import Path

import pytest
from test_infrastructure_smoke import fixture_smoke
from test_infrastructure_smoke import series as fixture_series

from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.experiment_preparation import prepare_experiment
from logicmus_eval.hashing import compute_file_sha256
from logicmus_eval.infrastructure_smoke import (
    SelectionRule,
    load_admitted_cases,
    prepare_selection,
    selection_digest,
    validate_selection,
)
from logicmus_eval.runner.config import InfrastructureSmokeConfig
from logicmus_eval.runner.preflight import build_request, preflight

smoke = fixture_smoke
series = fixture_series
MODEL_IDS = (
    "google/gemma-4-e4b",
    "openai/gpt-oss-20b",
    "qwen2.5-coder-14b-instruct",
)


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def pin(path):
    return {"path": str(path), "sha256": compute_file_sha256(path)}


@pytest.fixture(name="measurements")
def fixture_measurements(smoke, tmp_path):
    config, parent, _, original = smoke
    plan, _ = load_admitted_cases(parent)
    # Both an alternate seed and pair are admitted, so neither rejection can
    # accidentally pass merely because the substituted rule is unregistered.
    expanded = ExperimentPlan.model_validate(
        {**plan.model_dump(mode="json"), "pairs_per_seed": 2}
    )
    expanded_root = tmp_path / "expanded-parent"
    assert prepare_experiment(expanded, expanded_root).ready_for_evaluation
    parent = expanded_root / "series.manifest.json"
    config = config.model_copy(deep=True)
    config.series_manifest = str(parent)
    original = prepare_selection(
        parent,
        SelectionRule(
            selection_version="infrastructure-smoke-v1", seed=42, pair_index=0
        ),
        tmp_path / "base-selection.json",
    )
    plan, cases = load_admitted_cases(parent)
    base = set(original.case_uids)
    outsiders = sorted(case.case_id for case in cases if case.case_id not in base)
    tokenizer = tmp_path / "tokenizer.bin"
    template = tmp_path / "template.txt"
    source = tmp_path / "external-method.py"
    verification = tmp_path / "external-verification.txt"
    for path in (tokenizer, template, source, verification):
        path.write_text("synthetic fixture, not real exact-accounting evidence")
    scopes = []
    configurations = []
    for index, model_id in enumerate(MODEL_IDS):
        measured = config.model_copy(deep=True)
        measured.infrastructure_smoke = None
        measured.models[0].model_id = model_id
        measured.models[0].expected_profile.tokenizer = str(tokenizer)
        measured.models[0].expected_profile.chat_template = str(template)
        config_path = tmp_path / f"config-{index}.json"
        write_json(config_path, measured.model_dump(mode="json"))
        configurations.append(measured)
        for strategy in ("direct", "z3"):
            scope_index = len(scopes)
            inventory_path = tmp_path / f"lengths-{scope_index}.json"
            inventory = {
                "model_id": model_id,
                "strategy": strategy,
                "tokenizer": str(tokenizer),
                "chat_template": str(template),
                "measurements": [
                    {
                        "case_uid": case.case_id,
                        "request_sha256": hashlib.sha256(
                            json.dumps(
                                build_request(
                                    measured, measured.models[0], strategy, case
                                ),
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode("utf-8")
                        ).hexdigest(),
                        "input_tokens": 100
                        if case.case_id == outsiders[scope_index]
                        else 1,
                    }
                    for case in cases
                ],
            }
            write_json(inventory_path, inventory)
            evidence_path = tmp_path / f"method-{scope_index}.json"
            write_json(
                evidence_path,
                {
                    "evidence_version": "external-full-input-accounting-v1",
                    "method": "synthetic test fixture only",
                    "checked_by": "pytest synthetic fixture",
                    "checked_at": "2026-11-28",
                    "config_sha256": compute_file_sha256(config_path),
                    "inventory_sha256": compute_file_sha256(inventory_path),
                    "tokenizer_sha256": compute_file_sha256(tokenizer),
                    "chat_template_sha256": compute_file_sha256(template),
                    "covers_messages": True,
                    "covers_chat_template": True,
                    "covers_response_schema": True,
                    "covers_special_tokens": True,
                    "producer_sources": [pin(source)],
                    "verification_artifacts": [pin(verification)],
                },
            )
            scopes.append(
                {
                    "model_id": model_id,
                    "strategy": strategy,
                    "config": pin(config_path),
                    "inventory": pin(inventory_path),
                    "tokenizer": pin(tokenizer),
                    "chat_template": pin(template),
                    "accounting_evidence": pin(evidence_path),
                }
            )
    manifest_path = tmp_path / "measurements.json"
    manifest = {
        "measurement_version": "infrastructure-input-maxima-v1",
        "parent_manifest_sha256": compute_file_sha256(parent),
        "parent_plan_sha256": plan.plan_hash,
        "scopes": scopes,
    }
    write_json(manifest_path, manifest)
    return parent, original, outsiders, manifest_path, manifest, configurations


def make_rule(manifest_path):
    return SelectionRule.model_validate(
        {
            "selection_version": "infrastructure-smoke-v2",
            "seed": 42,
            "pair_index": 0,
            "measurement_manifest": pin(manifest_path),
            "base_selection": pin(manifest_path.parent / "base-selection.json"),
        }
    )


def repin_inventory(scope):
    scope["inventory"] = pin(Path(scope["inventory"]["path"]))
    path = Path(scope["accounting_evidence"]["path"])
    evidence = json.loads(path.read_text(encoding="utf-8"))
    evidence["inventory_sha256"] = scope["inventory"]["sha256"]
    write_json(path, evidence)
    scope["accounting_evidence"] = pin(path)


def test_v2_preserves_original_eight_adds_each_scope_maximum(measurements, tmp_path):
    parent, original, outsiders, manifest_path, _, configs = measurements
    path = tmp_path / "v2-selection.json"
    receipt = prepare_selection(parent, make_rule(manifest_path), path)
    assert receipt.case_uids == original.case_uids + outsiders[:6]
    assert len(receipt.case_uids) == 14
    _, cases = load_admitted_cases(parent)
    assert validate_selection(parent, path, cases) == receipt
    for config in configs:
        config.infrastructure_smoke = InfrastructureSmokeConfig(
            selection_path=str(path), selection_sha256=receipt.selection_sha256
        )
        # Revalidation is intentional: normal production configs are strict models.
        ready = preflight(type(config).model_validate(config.model_dump()))
        assert len(ready.jobs) == 28


def test_v2_ties_are_lexical_and_shared_maxima_deduplicate(measurements, tmp_path):
    parent, original, outsiders, manifest_path, manifest, _ = measurements
    for scope in manifest["scopes"]:
        path = Path(scope["inventory"]["path"])
        inventory = json.loads(path.read_text(encoding="utf-8"))
        for row in inventory["measurements"]:
            row["input_tokens"] = 50 if row["case_uid"] in outsiders[:2] else 1
        inventory["measurements"].reverse()
        write_json(path, inventory)
        repin_inventory(scope)
    manifest["scopes"].reverse()
    write_json(manifest_path, manifest)
    receipt = prepare_selection(parent, make_rule(manifest_path), tmp_path / "selected")
    assert receipt.case_uids == original.case_uids + outsiders[:1]


@pytest.mark.parametrize(
    "change",
    [
        "tokenizer_bytes",
        "template_bytes",
        "length_bytes",
        "config_bytes",
        "method_bytes",
    ],
)
def test_v2_rejects_pinned_artifact_changes(measurements, tmp_path, change):
    parent, _, _, manifest_path, manifest, _ = measurements
    rule = make_rule(manifest_path)
    key = {
        "tokenizer_bytes": "tokenizer",
        "template_bytes": "chat_template",
        "length_bytes": "inventory",
        "config_bytes": "config",
        "method_bytes": "accounting_evidence",
    }[change]
    Path(manifest["scopes"][0][key]["path"]).write_text("tampered", encoding="utf-8")
    with pytest.raises(ValueError):
        prepare_selection(parent, rule, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()


@pytest.mark.parametrize(
    "change", ["missing", "duplicate", "request", "zero", "tokenizer"]
)
def test_v2_checks_complete_requests_even_after_inventory_rehash(
    measurements, tmp_path, change
):
    parent, _, _, manifest_path, manifest, _ = measurements
    scope = manifest["scopes"][0]
    path = Path(scope["inventory"]["path"])
    inventory = json.loads(path.read_text(encoding="utf-8"))
    if change == "missing":
        inventory["measurements"].pop()
    elif change == "duplicate":
        inventory["measurements"][-1] = inventory["measurements"][0]
    elif change == "request":
        inventory["measurements"][0]["request_sha256"] = "0" * 64
    elif change == "zero":
        inventory["measurements"][0]["input_tokens"] = 0
    else:
        inventory["tokenizer"] = "different-tokenizer"
    write_json(path, inventory)
    repin_inventory(scope)
    write_json(manifest_path, manifest)
    with pytest.raises(ValueError):
        prepare_selection(parent, make_rule(manifest_path), tmp_path / "blocked")


@pytest.mark.parametrize(
    "change", ["missing_scope", "duplicate_scope", "parent", "schema_unmeasured"]
)
def test_v2_rejects_missing_scope_parent_or_full_accounting(
    measurements, tmp_path, change
):
    parent, _, _, manifest_path, manifest, _ = measurements
    if change == "missing_scope":
        manifest["scopes"].pop()
    elif change == "duplicate_scope":
        manifest["scopes"][-1] = manifest["scopes"][0]
    elif change == "parent":
        manifest["parent_manifest_sha256"] = "0" * 64
    else:
        scope = manifest["scopes"][0]
        path = Path(scope["accounting_evidence"]["path"])
        evidence = json.loads(path.read_text(encoding="utf-8"))
        evidence["covers_response_schema"] = False
        write_json(path, evidence)
        scope["accounting_evidence"] = pin(path)
    write_json(manifest_path, manifest)
    with pytest.raises(ValueError):
        prepare_selection(parent, make_rule(manifest_path), tmp_path / "blocked")


def test_v2_reproduces_membership_and_runtime_conditions(measurements, tmp_path):
    parent, _, _, manifest_path, _, configs = measurements
    path = tmp_path / "selected"
    receipt = prepare_selection(parent, make_rule(manifest_path), path)
    _, cases = load_admitted_cases(parent)
    payload = receipt.model_dump(mode="json")
    payload["case_uids"] = payload["case_uids"][:-1]
    payload["selection_sha256"] = selection_digest(payload)
    write_json(path, payload)
    with pytest.raises(ValueError):
        validate_selection(parent, path, cases)
    write_json(path, receipt.model_dump(mode="json"))
    changed = configs[0].model_copy(deep=True)
    changed.models[0].expected_profile.tokenizer = "different"
    with pytest.raises(ValueError):
        validate_selection(parent, path, cases, config=changed)


def test_v1_serialization_and_receipt_remain_identical(smoke, tmp_path):
    _, parent, _, receipt = smoke
    rule = SelectionRule(
        selection_version="infrastructure-smoke-v1", seed=42, pair_index=0
    )
    assert rule.model_dump(mode="json") == {
        "selection_version": "infrastructure-smoke-v1",
        "seed": 42,
        "pair_index": 0,
    }
    assert prepare_selection(parent, rule, tmp_path / "v1") == receipt


def test_v2_requires_an_immutable_original_v1_base_pin(measurements):
    payload = make_rule(measurements[3]).model_dump(mode="json")
    payload.pop("base_selection", None)
    with pytest.raises(ValueError):
        SelectionRule.model_validate(payload)


@pytest.mark.parametrize("field,value", [("seed", 44), ("pair_index", 1)])
def test_v2_cannot_replace_original_eight_with_another_registered_rule(
    measurements, tmp_path, field, value
):
    parent, _, _, manifest_path, _, _ = measurements
    rule = make_rule(manifest_path)
    setattr(rule, field, value)
    with pytest.raises(ValueError):
        prepare_selection(parent, rule, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()


@pytest.mark.parametrize(
    "change",
    ["bytes", "membership", "order", "rule", "parent", "plan", "v2", "v2_rule"],
)
def test_v2_independently_reproduces_pinned_original_v1_base(
    measurements, tmp_path, change
):
    parent, original, outsiders, manifest_path, _, _ = measurements
    rule = make_rule(manifest_path)
    path = manifest_path.parent / "base-selection.json"
    payload = original.model_dump(mode="json")
    if change == "membership":
        payload["case_uids"][0] = outsiders[0]
    elif change == "order":
        payload["case_uids"].reverse()
    elif change == "rule":
        payload["rule"]["seed"] = 44
    elif change == "parent":
        payload["parent_manifest_sha256"] = "0" * 64
    elif change == "plan":
        payload["parent_plan_sha256"] = "0" * 64
    elif change == "v2":
        payload["selection_version"] = "infrastructure-smoke-v2"
        payload["rule"] = rule.model_dump(mode="json")
    elif change == "v2_rule":
        payload["rule"] = rule.model_dump(mode="json")
    else:
        payload["case_uids"][0] = outsiders[0]
    payload["selection_sha256"] = selection_digest(payload)
    write_json(path, payload)
    if change != "bytes":
        updated = rule.model_dump(mode="json")
        updated["base_selection"] = pin(path)
        rule = SelectionRule.model_validate(updated)
    with pytest.raises(ValueError):
        prepare_selection(parent, rule, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()


def test_v2_rejects_a_valid_v1_base_from_another_admitted_parent(
    measurements, smoke, tmp_path
):
    parent, _, _, manifest_path, _, _ = measurements
    _, other_parent, other_selection_path, _ = smoke
    _, other_cases = load_admitted_cases(other_parent)
    validate_selection(other_parent, other_selection_path, other_cases)
    payload = make_rule(manifest_path).model_dump(mode="json")
    payload["base_selection"] = pin(other_selection_path)
    with pytest.raises(ValueError):
        prepare_selection(
            parent, SelectionRule.model_validate(payload), tmp_path / "blocked"
        )


def test_v1_cannot_acquire_a_base_selection_pin(measurements):
    payload = {
        "selection_version": "infrastructure-smoke-v1",
        "seed": 42,
        "pair_index": 0,
        "base_selection": pin(measurements[3].parent / "base-selection.json"),
    }
    with pytest.raises(ValueError):
        SelectionRule.model_validate(payload)


@pytest.mark.parametrize("change", ["leakage", "unselected_case", "combined"])
def test_v2_requires_the_entire_parent_admitted(measurements, tmp_path, change):
    parent, original, _, manifest_path, _, _ = measurements
    rule = make_rule(manifest_path)
    manifest = json.loads(parent.read_text(encoding="utf-8"))
    if change == "leakage":
        manifest["cells"][0]["leakage_report"]["global_word"][
            "mean_balanced_accuracy"
        ] = 0.9
        write_json(parent, manifest)
    else:
        key = "combined_path" if change == "combined" else "dataset_path"
        item = manifest if change == "combined" else manifest["cells"][0]
        artifact = parent.parent / item[key]
        rows = artifact.read_text(encoding="utf-8").splitlines()
        index = next(
            i
            for i, line in enumerate(rows)
            if json.loads(line)["case_id"] not in original.case_uids
        )
        row = json.loads(rows[index])
        row["metadata"]["purpose"] = "confirmation"
        rows[index] = json.dumps(row)
        artifact.write_text("\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        prepare_selection(parent, rule, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()


def test_v2_rejects_even_a_fully_admitted_confirmation_parent(
    measurements, series, tmp_path
):
    _, manifest = series
    plan = ExperimentPlan.model_validate(
        dict(manifest.plan, purpose="confirmation", seeds=[43])
    )
    destination = tmp_path / "confirmation"
    admitted = prepare_experiment(plan, destination)
    assert admitted.ready_for_evaluation
    rule = make_rule(measurements[3])
    rule.seed = 43
    with pytest.raises(ValueError, match="development"):
        prepare_selection(
            destination / "series.manifest.json", rule, tmp_path / "blocked"
        )


@pytest.mark.parametrize(
    "change", ["tokenizer", "chat_template", "max_tokens", "endpoint", "timeout"]
)
def test_v2_runtime_must_use_the_measured_exact_conditions(
    measurements, tmp_path, change
):
    parent, _, _, manifest_path, _, configs = measurements
    path = tmp_path / "selected"
    prepare_selection(parent, make_rule(manifest_path), path)
    _, cases = load_admitted_cases(parent)
    changed = configs[0].model_copy(deep=True)
    if change in {"tokenizer", "chat_template"}:
        setattr(changed.models[0].expected_profile, change, "different")
    elif change == "max_tokens":
        changed.models[0].generation.max_tokens += 1
    elif change == "endpoint":
        changed.endpoint = "http://localhost:9999/v1"
    else:
        changed.request_timeout_seconds += 1
    with pytest.raises(ValueError):
        validate_selection(parent, path, cases, config=changed)


def test_v2_external_method_implementation_is_pinned(measurements, tmp_path):
    parent, _, _, manifest_path, manifest, _ = measurements
    scope = manifest["scopes"][0]
    evidence = json.loads(
        Path(scope["accounting_evidence"]["path"]).read_text(encoding="utf-8")
    )
    Path(evidence["producer_sources"][0]["path"]).write_text(
        "substituted accounting implementation", encoding="utf-8"
    )
    with pytest.raises(ValueError):
        prepare_selection(parent, make_rule(manifest_path), tmp_path / "blocked")


def test_v2_resolves_pins_and_measured_configs_relative_to_their_files(
    measurements, tmp_path
):
    parent, original, outsiders, manifest_path, manifest, _ = measurements
    for scope in manifest["scopes"]:
        config_path = Path(scope["config"]["path"])
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["series_manifest"] = "expanded-parent/series.manifest.json"
        write_json(config_path, config)
        scope["config"] = pin(config_path)
        evidence_path = Path(scope["accounting_evidence"]["path"])
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        evidence["config_sha256"] = scope["config"]["sha256"]
        for key in ("producer_sources", "verification_artifacts"):
            for artifact in evidence[key]:
                artifact["path"] = Path(artifact["path"]).name
        write_json(evidence_path, evidence)
        scope["accounting_evidence"] = pin(evidence_path)
        for key in (
            "config",
            "inventory",
            "tokenizer",
            "chat_template",
            "accounting_evidence",
        ):
            scope[key]["path"] = Path(scope[key]["path"]).name
    write_json(manifest_path, manifest)
    payload = make_rule(manifest_path).model_dump(mode="json")
    payload["measurement_manifest"]["path"] = "../measurements.json"
    payload["base_selection"]["path"] = "../base-selection.json"
    receipt = prepare_selection(
        parent, SelectionRule.model_validate(payload), tmp_path / "relative-selected"
    )
    assert receipt.case_uids == original.case_uids + outsiders[:6]
