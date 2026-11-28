"""Fixed, parent-bound infrastructure samples, with no research admission waiver."""

import json
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from logicmus_eval.experiment_plan import ExperimentPlan, content_id
from logicmus_eval.hashing import compute_file_sha256
from logicmus_eval.models.evaluation import ExperimentProvenance
from logicmus_eval.models.test_case import LogicTestCase
from logicmus_eval.release import assert_controlled_series_approved
from logicmus_eval.runner.config import RunConfig, StrictModel
from logicmus_eval.smoke_input_selection import FilePin, maximum_input_cases


class SelectionRule(StrictModel):
    selection_version: Literal["infrastructure-smoke-v1", "infrastructure-smoke-v2"]
    seed: int = Field(ge=0)
    pair_index: int = Field(ge=0)
    # Omission preserves the exact historical v1 payload/digest.
    measurement_manifest: FilePin | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    base_selection: FilePin | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @model_validator(mode="after")
    def check_measurement_version(self) -> Self:
        is_v2 = self.selection_version == "infrastructure-smoke-v2"
        if any(
            (pin is not None) != is_v2
            for pin in (self.measurement_manifest, self.base_selection)
        ):
            raise ValueError(
                "Only v2 requires both pinned original v1 selection and input measurements"
            )
        return self


class InfrastructureSelection(StrictModel):
    selection_version: Literal["infrastructure-smoke-v1", "infrastructure-smoke-v2"]
    purpose: Literal["infrastructure-smoke"] = "infrastructure-smoke"
    parent_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    parent_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rule: SelectionRule
    case_uids: list[str] = Field(min_length=1, max_length=16)
    standalone_research_admission: Literal["not_admitted"] = "not_admitted"
    leakage_status: Literal["not_applicable_infrastructure_subset"] = (
        "not_applicable_infrastructure_subset"
    )
    selection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def selection_digest(payload: dict[str, Any]) -> str:
    return content_id(
        {key: value for key, value in payload.items() if key != "selection_sha256"}
    )


def load_admitted_cases(parent: Path) -> tuple[ExperimentPlan, list[LogicTestCase]]:
    """Verify ALL parent artifacts and admission before exposing any selected row."""
    manifest = assert_controlled_series_approved(parent)
    plan = ExperimentPlan.model_validate(manifest.plan)
    cases: list[LogicTestCase] = []
    for item in manifest.cells:
        rows = [
            LogicTestCase.model_validate_json(line)
            for line in (parent.parent / str(item.dataset_path))
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        expected = {record["case_id"] for record in item.smt_checks}
        if len(rows) != len(expected) or {row.case_id for row in rows} != expected:
            raise ValueError("Dataset cases differ from admitted cell evidence")
        for row in rows:
            provenance = ExperimentProvenance.model_validate(row.metadata)
            if not all(
                (
                    provenance.case_uid == row.case_id,
                    provenance.cell_id == item.cell.cell_id,
                    provenance.total_rules == item.cell.n,
                    row.mus_size == item.cell.k,
                    provenance.purpose == plan.purpose,
                    provenance.protocol_version == plan.protocol_version,
                )
            ):
                raise ValueError("Dataset case provenance differs from plan")
        cases.extend(rows)
    combined = [
        json.loads(line)
        for line in (parent.parent / str(manifest.combined_path))
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    if combined != [case.model_dump(mode="json") for case in cases]:
        raise ValueError("Combined dataset differs from planned cell contents")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("Duplicate case_uid")
    return plan, cases


def _selection(
    parent: Path,
    rule: SelectionRule,
    plan: ExperimentPlan,
    cases: list[LogicTestCase],
    config: RunConfig | None = None,
) -> InfrastructureSelection:
    if plan.purpose != "development" or any(
        case.metadata.get("purpose") != "development" for case in cases
    ):
        raise ValueError("Infrastructure smoke requires a development parent")
    if rule.seed not in plan.seeds or rule.pair_index >= plan.pairs_per_seed:
        raise ValueError("Smoke selection rule is not registered in parent")
    selected = [
        case
        for case in cases
        if case.metadata["seed"] == rule.seed
        and case.metadata["pair_index"] == rule.pair_index
    ]
    # Every cell is included: no access to a passing cell of a failed series,
    # and the maximum registered N is necessarily exercised in each domain.
    if len(selected) != 2 * len(plan.cells()):
        raise ValueError("Smoke selection must include one pair from every parent cell")
    if {
        (case.metadata["pattern_id"] == "math", case.is_satisfiable)
        for case in selected
    } != {(numeric, sat) for numeric in (False, True) for sat in (False, True)}:
        raise ValueError("Smoke requires Boolean/numeric SAT/UNSAT coverage")
    selected_ids = [case.case_id for case in selected]
    if rule.measurement_manifest is not None:
        selected_ids = _original_selection(parent, rule, plan, cases)
        selected_ids = list(
            dict.fromkeys(
                selected_ids
                + maximum_input_cases(
                    parent, plan, cases, rule.measurement_manifest, config
                )
            )
        )
        if len(selected_ids) > 14:
            raise ValueError(
                "V2 infrastructure smoke may select at most fourteen cases"
            )
    payload = {
        "selection_version": rule.selection_version,
        "purpose": "infrastructure-smoke",
        "parent_manifest_sha256": compute_file_sha256(parent),
        "parent_plan_sha256": plan.plan_hash,
        "rule": rule.model_dump(mode="json"),
        "case_uids": selected_ids,
        "standalone_research_admission": "not_admitted",
        "leakage_status": "not_applicable_infrastructure_subset",
    }
    return InfrastructureSelection.model_validate(
        {**payload, "selection_sha256": selection_digest(payload)}
    )


def _original_selection(
    parent: Path,
    rule: SelectionRule,
    plan: ExperimentPlan,
    cases: list[LogicTestCase],
) -> list[str]:
    if rule.base_selection is None:
        raise ValueError("V2 requires a pinned original v1 selection")
    path = rule.base_selection.verify(parent.parent)
    original = InfrastructureSelection.model_validate_json(
        path.read_text(encoding="utf-8")
    )
    # Check both versions before recomputation: a v2 receipt can never recurse
    # into another base selection or substitute its enlarged membership.
    if original.selection_version != "infrastructure-smoke-v1" or (
        original.rule.selection_version != "infrastructure-smoke-v1"
    ):
        raise ValueError("V2 base selection must be an original v1 receipt")
    if original != _selection(parent, original.rule, plan, cases):
        raise ValueError("Original v1 selection differs from admitted parent/rule/hash")
    if (rule.seed, rule.pair_index) != (
        original.rule.seed,
        original.rule.pair_index,
    ):
        raise ValueError("V2 seed/pair must preserve the pinned original v1 selection")
    if len(original.case_uids) != 8:
        raise ValueError("V2 preserves exactly eight original seed/pair cases")
    return list(original.case_uids)


def prepare_selection(
    parent_manifest: Path, rule: SelectionRule, output: Path
) -> InfrastructureSelection:
    """Offline one-shot selection from a fully admitted parent; no endpoint access."""
    parent = parent_manifest.resolve()
    plan, cases = load_admitted_cases(parent)
    receipt = _selection(parent, rule, plan, cases)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return receipt


def validate_selection(
    parent_manifest: Path,
    selection_path: Path,
    cases: list[LogicTestCase],
    *,
    config: RunConfig | None = None,
) -> InfrastructureSelection:
    receipt = InfrastructureSelection.model_validate_json(
        selection_path.read_text(encoding="utf-8")
    )
    plan, admitted = load_admitted_cases(parent_manifest)
    if admitted != cases or receipt != _selection(
        parent_manifest, receipt.rule, plan, admitted, config
    ):
        raise ValueError(
            "Smoke selection differs from admitted parent or fixed rule/hash"
        )
    return receipt
