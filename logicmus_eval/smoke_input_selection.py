"""Input-only maxima from externally verified, immutable full-input measurements.

This module verifies the scope, pins and request identities of supplied external
evidence. It does not establish a tokenizer/accounting method, contact a backend,
or turn a table labelled ``exact`` into proof of full HTTP-input accounting.
The producer and verification artifacts must establish that prerequisite before
an operator freezes the rule. Synthetic test artifacts are never real evidence.
"""

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import Field

from logicmus_eval.experiment_plan import ExperimentPlan, canonical_json
from logicmus_eval.hashing import compute_file_sha256
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.runner.config import RunConfig, StrictModel, load_config
from logicmus_eval.runner.requests import build_request

SMOKE_MODEL_IDS = frozenset(
    {"google/gemma-4-e4b", "openai/gpt-oss-20b", "qwen2.5-coder-14b-instruct"}
)


class FilePin(StrictModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    def verify(self, root: Path) -> Path:
        path = (root / self.path).resolve()
        if compute_file_sha256(path) != self.sha256:
            raise ValueError(f"Pinned input measurement artifact differs: {path}")
        return path


class InputLength(StrictModel):
    case_uid: str = Field(min_length=1)
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_tokens: int = Field(gt=0)


class InputInventory(StrictModel):
    model_id: str = Field(min_length=1)
    strategy: Literal["direct", "z3"]
    tokenizer: str = Field(min_length=1)
    chat_template: str = Field(min_length=1)
    measurements: list[InputLength] = Field(min_length=1)


class ExternalAccountingEvidence(StrictModel):
    """External method attestation plus pinned implementation and verification.

    Coverage declarations alone are insufficient: source and verification files
    are mandatory and remain available for independent review of exactness.
    """

    evidence_version: Literal["external-full-input-accounting-v1"]
    method: str = Field(min_length=1)
    checked_by: str = Field(min_length=1)
    checked_at: str = Field(min_length=1)
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    tokenizer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    chat_template_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    covers_messages: Literal[True]
    covers_chat_template: Literal[True]
    covers_response_schema: Literal[True]
    covers_special_tokens: Literal[True]
    producer_sources: list[FilePin] = Field(min_length=1)
    verification_artifacts: list[FilePin] = Field(min_length=1)


class MeasurementScope(StrictModel):
    model_id: str = Field(min_length=1)
    strategy: Literal["direct", "z3"]
    config: FilePin
    inventory: FilePin
    tokenizer: FilePin
    chat_template: FilePin
    accounting_evidence: FilePin


class MeasurementManifest(StrictModel):
    measurement_version: Literal["infrastructure-input-maxima-v1"]
    parent_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    scopes: list[MeasurementScope] = Field(min_length=6, max_length=6)


def _external_evidence(root: Path, scope: MeasurementScope) -> None:
    path = scope.accounting_evidence.verify(root)
    evidence = ExternalAccountingEvidence.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    if (
        evidence.config_sha256 != scope.config.sha256
        or evidence.inventory_sha256 != scope.inventory.sha256
        or evidence.tokenizer_sha256 != scope.tokenizer.sha256
        or evidence.chat_template_sha256 != scope.chat_template.sha256
    ):
        raise ValueError("External full-input evidence refers to different artifacts")
    for artifact in (*evidence.producer_sources, *evidence.verification_artifacts):
        source = artifact.verify(path.parent)
        if source.stat().st_size == 0:
            raise ValueError(
                "External accounting source/verification artifact is empty"
            )


def _same_runtime_conditions(actual: RunConfig, measured: RunConfig) -> None:
    excluded = {"series_manifest", "infrastructure_smoke", "models"}
    if actual.model_dump(exclude=excluded) != measured.model_dump(exclude=excluded):
        raise ValueError("Smoke runtime configuration differs from measured conditions")
    model = measured.models[0]
    matches = [item for item in actual.models if item.model_id == model.model_id]
    if len(matches) != 1 or matches[0] != model:
        raise ValueError("Smoke runtime model/profile differs from measured conditions")


def _scope_maximum(  # pylint: disable=too-many-locals
    root: Path,
    scope: MeasurementScope,
    parent: Path,
    cases: list[LogicTestCase],
    runtime: RunConfig | None,
) -> str:
    config = load_config(scope.config.verify(root))
    if (
        Path(config.series_manifest).resolve() != parent.resolve()
        or config.infrastructure_smoke is not None
        or len(config.models) != 1
        or config.models[0].model_id != scope.model_id
        or set(config.strategies) != {"direct", "z3"}
    ):
        raise ValueError("Input measurement config must describe the complete parent")
    if config.diagnostic_parent_run is not None:
        raise ValueError("Input measurement config cannot select a diagnostic rerun")
    if runtime is not None and scope.model_id in {
        model.model_id for model in runtime.models
    }:
        _same_runtime_conditions(runtime, config)
    model = config.models[0]
    scope.tokenizer.verify(root)
    scope.chat_template.verify(root)
    _external_evidence(root, scope)
    inventory = InputInventory.model_validate_json(
        scope.inventory.verify(root).read_text(encoding="utf-8")
    )
    if (
        inventory.model_id != scope.model_id
        or inventory.strategy != scope.strategy
        or inventory.tokenizer != model.expected_profile.tokenizer
        or inventory.chat_template != model.expected_profile.chat_template
    ):
        raise ValueError(
            "Input inventory model/strategy/tokenizer/chat template differs"
        )
    records = {record.case_uid: record for record in inventory.measurements}
    if len(records) != len(inventory.measurements) or records.keys() != {
        case.case_id for case in cases
    }:
        raise ValueError("Input measurements must cover every parent case once")
    expected = [
        hashlib.sha256(
            canonical_json(build_request(config, model, scope.strategy, case)).encode(
                "utf-8"
            )
        ).hexdigest()
        for case in cases
    ]
    observed = [records[case.case_id].request_sha256 for case in cases]
    if observed != expected or len(set(observed)) != len(observed):
        raise ValueError("Input measurements differ from exact production requests")
    return min(records, key=lambda uid: (-records[uid].input_tokens, uid))


def maximum_input_cases(
    parent: Path,
    plan: ExperimentPlan,
    cases: list[LogicTestCase],
    manifest_pin: FilePin,
    runtime: RunConfig | None = None,
) -> list[str]:
    """Verify all six full-parent inventories and return their deterministic maxima."""
    path = manifest_pin.verify(parent.parent)
    manifest = MeasurementManifest.model_validate_json(path.read_text(encoding="utf-8"))
    expected = {
        (model, strategy) for model in SMOKE_MODEL_IDS for strategy in ("direct", "z3")
    }
    observed = [(scope.model_id, scope.strategy) for scope in manifest.scopes]
    if len(set(observed)) != len(observed) or set(observed) != expected:
        raise ValueError("Input maxima require all three models and both strategies")
    if (
        manifest.parent_manifest_sha256 != compute_file_sha256(parent)
        or manifest.parent_plan_sha256 != plan.plan_hash
    ):
        raise ValueError("Input measurement parent/plan differs")
    if runtime is not None and (
        Path(runtime.series_manifest).resolve() != parent.resolve()
        or not {model.model_id for model in runtime.models} <= SMOKE_MODEL_IDS
    ):
        raise ValueError("Smoke runtime parent/model differs from measured scopes")
    return [
        _scope_maximum(path.parent, scope, parent, cases, runtime)
        for scope in sorted(
            manifest.scopes, key=lambda item: (item.model_id, item.strategy)
        )
    ]
