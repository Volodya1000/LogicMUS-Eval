import json
import subprocess
import sys

import pytest
import z3
from typer.testing import CliRunner

from logicmus_eval import evaluate_llm, experiment_preparation
from logicmus_eval.cli import app
from logicmus_eval.controlled_generation import generate_cell
from logicmus_eval.experiment_plan import ExperimentPlan
from logicmus_eval.experiment_preparation import prepare_experiment
from logicmus_eval.hashing import compute_file_sha256
from logicmus_eval.leakage import calculate_leakage, case_group, grouped_splits
from logicmus_eval.models.manifests import TfidfMetrics
from logicmus_eval.models.pipeline import LeakageReport
from logicmus_eval.models.rules import NoiseRule
from logicmus_eval.release import assert_dataset_approved
from logicmus_eval.storage import FileStorageManager


def test_offline_cli_does_not_import_model_client():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import logicmus_eval.cli; assert 'litellm' not in sys.modules",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def small_plan():
    return ExperimentPlan.model_validate(
        {
            "protocol_version": "controlled-v1",
            "purpose": "development",
            "seeds": [42],
            "pairs_per_seed": 1,
            "series": [
                {
                    "series_id": "tiny",
                    "kind": "noise_sweep",
                    "patterns": [{"pattern_id": "fork", "k_values": [3]}],
                    "n_values": [4, 7],
                }
            ],
        }
    )


def test_related_n_variants_share_all_leakage_folds():
    plan = small_plan().model_copy(update={"pairs_per_seed": 5})
    dataset = [x for cell in plan.cells() for x in generate_cell(plan, cell)]
    groups = [case_group(x) for x in dataset]
    assert len(set(groups)) == 5
    for train, test in grouped_splits([int(x.is_satisfiable) for x in dataset], groups):
        assert {groups[i] for i in train}.isdisjoint({groups[i] for i in test})
    # Both real model-visible views are evaluated with this grouping.
    report = calculate_leakage(dataset, [3])
    assert report.by_input["direct"]["global"]["word_tfidf"].n_splits == 5


def test_failed_audit_preserves_all_cells_and_blocks_evaluation(tmp_path):
    plan = small_plan()
    manifest = prepare_experiment(plan, tmp_path)
    assert not manifest.ready_for_evaluation
    assert manifest.plan_sha256 == plan.plan_hash
    assert len(manifest.cells) == 2
    assert all(cell.smt_passed and cell.reference_passed for cell in manifest.cells)
    assert all(cell.dataset_sha256 for cell in manifest.cells)
    assert all(not cell.leakage_acceptance.passed for cell in manifest.cells)
    assert manifest.plan["seeds"] == [42]
    assert manifest.plan["pairs_per_seed"] == 1
    assert manifest.plan["leakage_threshold"] == 0.55
    for cell in manifest.cells:
        with pytest.raises(ValueError, match="not approved"):
            assert_dataset_approved(tmp_path / cell.dataset_path)
    alias = tmp_path / "renamed.jsonl"
    alias.write_bytes((tmp_path / manifest.cells[0].dataset_path).read_bytes())
    with pytest.raises(ValueError, match="not approved"):
        assert_dataset_approved(alias)


def test_same_plan_reproduces_all_content_hashes_and_manifest(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    a = prepare_experiment(small_plan(), first)
    b = prepare_experiment(small_plan(), second)
    assert a.model_dump() == b.model_dump()
    assert compute_file_sha256(first / "series.manifest.json") == compute_file_sha256(
        second / "series.manifest.json"
    )
    for artifact in a.cells:
        assert (
            compute_file_sha256(first / artifact.dataset_path)
            == artifact.dataset_sha256
        )
        assert (
            compute_file_sha256(first / artifact.reference_path)
            == artifact.reference_sha256
        )


@pytest.mark.parametrize("error_type", [ValueError, TypeError, KeyError])
def test_cell_failure_is_recorded_and_later_cells_still_processed(
    tmp_path, monkeypatch, error_type
):
    real_generate = experiment_preparation.generate_cell

    def broken(plan, cell):
        if cell.n == 4:
            raise error_type("injected construction failure")
        return real_generate(plan, cell)

    monkeypatch.setattr(experiment_preparation, "generate_cell", broken)
    result = prepare_experiment(small_plan(), tmp_path)
    assert not result.ready_for_evaluation
    assert len(result.cells) == 2
    assert "injected construction failure" in str(result.cells[0].failures)
    assert result.cells[1].dataset_path


def test_preflight_validates_entire_plan_before_writing(tmp_path):
    plan = small_plan()
    plan.series[0].n_values.append(3)
    with pytest.raises(ValueError, match="construction"):
        prepare_experiment(plan, tmp_path / "untouched")
    assert not (tmp_path / "untouched").exists()


def test_cli_reports_nonready_series_without_models(tmp_path):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(small_plan().model_dump()), encoding="utf-8")
    result = CliRunner().invoke(
        app,
        [
            "prepare-experiment",
            "--plan",
            str(plan_path),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 1
    assert "not ready" in result.output
    assert (tmp_path / "out" / "series.manifest.json").exists()


@pytest.fixture(name="accepted_series")
def fixture_accepted_series(tmp_path, monkeypatch):
    """Isolate release-gate behavior from statistical variation in tiny probes."""

    def measured_probe(_dataset, ks):
        metric = TfidfMetrics(
            mean_balanced_accuracy=0.5,
            status="ok",
            n_splits=2,
            fold_balanced_accuracies=[0.5, 0.5],
        )
        groups = {
            name: {"word_tfidf": metric, "char_tfidf": metric}
            for name in ["global", *(f"mus_size={k}" for k in ks)]
        }
        return LeakageReport(
            global_word=metric,
            global_char=metric,
            by_mus_size={
                key: value for key, value in groups.items() if key != "global"
            },
            by_input={"direct": groups, "z3": groups},
        )

    monkeypatch.setattr(experiment_preparation, "calculate_leakage", measured_probe)
    plan = small_plan().model_copy(update={"pairs_per_seed": 2})
    manifest = prepare_experiment(plan, tmp_path)
    assert manifest.ready_for_evaluation
    return tmp_path, manifest


def test_approved_series_checks_hashes_of_every_cell_and_reference(accepted_series):
    root, manifest = accepted_series
    selected = root / manifest.cells[0].dataset_path
    assert_dataset_approved(selected)
    assert_dataset_approved(root / manifest.combined_path)
    other_reference = root / manifest.cells[1].reference_path
    other_reference.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash differs"):
        assert_dataset_approved(selected)


def test_stored_scores_must_support_summary_acceptance(accepted_series):
    root, manifest = accepted_series
    metric = manifest.cells[0].leakage_report.by_input["z3"]["global"]["char_tfidf"]
    metric.mean_balanced_accuracy = 1.0
    metric.fold_balanced_accuracies = [1.0, 1.0]
    (root / "series.manifest.json").write_text(
        manifest.model_dump_json(), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="failed mandatory"):
        assert_dataset_approved(root / manifest.combined_path)


def test_missing_cell_cannot_be_hidden_by_ready_flag(accepted_series):
    root, manifest = accepted_series
    manifest.cells.pop()
    (root / "series.manifest.json").write_text(
        manifest.model_dump_json(), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="failed mandatory"):
        assert_dataset_approved(root / manifest.combined_path)


def test_broken_primary_encoding_is_detected_by_reference_control(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(NoiseRule, "to_z3", lambda _rule: z3.BoolVal(False))
    manifest = prepare_experiment(small_plan(), tmp_path)
    assert manifest.cells[0].smt_passed  # N=4 has no independent noise.
    assert not manifest.cells[1].smt_passed
    assert manifest.cells[1].reference_passed
    assert not manifest.ready_for_evaluation


def test_failed_series_never_constructs_model_extractor(tmp_path, monkeypatch):
    manifest = prepare_experiment(small_plan(), tmp_path)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Failed series reached model construction")

    monkeypatch.setattr(evaluate_llm, "StructuredOutputExtractor", forbidden)
    with pytest.raises(ValueError, match="not approved"):
        evaluate_llm.run_evaluation(
            str(tmp_path / manifest.cells[0].dataset_path.rsplit("/", 1)[0]),
            "unused",
            "direct",
            2,
            "unused.json",
        )


@pytest.mark.parametrize(
    "filename", ["dataset_controlled.jsonl", "combined_controlled.jsonl"]
)
def test_empty_controlled_file_still_requires_manifest(tmp_path, filename):
    dataset = tmp_path / filename
    dataset.write_bytes(b"")
    with pytest.raises(ValueError, match="not approved"):
        assert_dataset_approved(dataset)


def test_controlled_file_with_legacy_replacement_still_checks_hash(accepted_series):
    root, manifest = accepted_series
    dataset = root / manifest.combined_path
    dataset.write_text('{"case_id":"legacy","metadata":{}}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="hash differs"):
        assert_dataset_approved(dataset)


@pytest.mark.parametrize("stage", ["cell", "combined"])
def test_actual_serialized_dataset_is_checked(tmp_path, monkeypatch, stage):
    original = FileStorageManager.save_dataset

    def corrupt(storage, filename, dataset):
        path = original(storage, filename, dataset)
        if filename == (
            "dataset_controlled.jsonl"
            if stage == "cell"
            else "combined_controlled.jsonl"
        ):
            rows = [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
            ]
            for row in rows:
                if not row["is_satisfiable"]:
                    for rule in row["rules"]:
                        if rule["operator_type"] == "TERMINAL":
                            rule["polarity"] = not rule["polarity"]
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
            )
        return path

    monkeypatch.setattr(FileStorageManager, "save_dataset", corrupt)
    manifest = prepare_experiment(small_plan(), tmp_path)
    assert not manifest.ready_for_evaluation
    if stage == "cell":
        assert all(not cell.reference_passed for cell in manifest.cells)
        assert all(
            any("serialized" in failure for failure in cell.failures)
            for cell in manifest.cells
        )
    else:
        assert any("serialized" in failure for failure in manifest.failures)


@pytest.mark.parametrize("alteration", ["smt_records", "grouping", "fold_count"])
def test_release_requires_case_bound_evidence_and_real_family_folds(
    accepted_series, alteration
):
    root, manifest = accepted_series
    if alteration == "smt_records":
        for cell in manifest.cells:
            cell.smt_checks = [{"passed": True}] * len(cell.smt_checks)
            cell.reference_checks = [{"passed": True}] * len(cell.reference_checks)
    elif alteration == "grouping":
        manifest.cv_grouping = "pair_id"
    else:
        for cell in manifest.cells:
            for view in cell.leakage_report.by_input.values():
                for group in view.values():
                    for metric in group.values():
                        metric.n_splits = 5
                        metric.fold_balanced_accuracies = [0.5] * 5
    (root / "series.manifest.json").write_text(
        manifest.model_dump_json(), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="not approved"):
        assert_dataset_approved(root / manifest.combined_path)


def test_unrelated_external_protocol_stays_legacy_readable(tmp_path):
    dataset = tmp_path / "external.jsonl"
    dataset.write_text(
        '{"metadata":{"protocol_version":"external-v1"}}\n', encoding="utf-8"
    )
    assert_dataset_approved(dataset)
