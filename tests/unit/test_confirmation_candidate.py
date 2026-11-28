"""Candidate receipts protect science but never grant release admission."""

import json
import shutil
from pathlib import Path

import pytest

from logicmus_eval.confirmation.launch import initialize_release
from logicmus_eval.confirmation.service import verify_release
from scripts import confirmation_candidate as candidate


@pytest.fixture(name="candidate_root")
def fixture_candidate_root(tmp_path):
    root = tmp_path / "candidate"
    root.mkdir()
    original = Path("releases/confirmation-v2-candidate")
    for name in candidate.CONTRACTS:
        shutil.copyfile(original / name, root / name)
    repository = tmp_path / "repo"
    (repository / "logicmus_eval").mkdir(parents=True)
    (repository / "logicmus_eval" / "example.py").write_text("VALUE = 1\n")
    (repository / "scripts").mkdir()
    (repository / "scripts" / "confirmation_candidate.py").write_text("# helper\n")
    for name in ("uv.lock", "pyproject.toml"):
        (repository / name).write_text("original\n")
    return root, repository


def test_candidate_refuses_second_freeze_and_preexisting_data(candidate_root):
    root, repository = candidate_root
    candidate.freeze(root, repository)
    original = (root / "candidate.receipt.json").read_bytes()
    with pytest.raises((ValueError, FileExistsError)):
        candidate.freeze(root, repository)
    assert (root / "candidate.receipt.json").read_bytes() == original
    other = root.parent / "already-prepared"
    shutil.copytree(root, other)
    (other / "candidate.receipt.json").unlink()
    (other / "bundle").mkdir()
    with pytest.raises(ValueError, match="preparation"):
        candidate.freeze(other, repository)


@pytest.mark.parametrize("target", ["plan", "source", "lock", "helper"])
def test_candidate_detects_changed_inputs(candidate_root, target):
    root, repository = candidate_root
    candidate.freeze(root, repository)
    paths = {
        "plan": root / "confirmation.plan.json",
        "source": repository / "logicmus_eval" / "example.py",
        "lock": repository / "uv.lock",
        "helper": repository / "scripts" / "confirmation_candidate.py",
    }
    with paths[target].open("a", encoding="utf-8") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="changed"):
        candidate.verify(root, repository)


def test_attempt_marker_blocks_a_second_preparation(candidate_root):
    root, repository = candidate_root
    candidate.freeze(root, repository)
    candidate.begin_preparation(root, repository)
    marker = (root / "preparation.attempt.json").read_bytes()
    with pytest.raises((ValueError, FileExistsError)):
        candidate.begin_preparation(root, repository)
    assert (root / "preparation.attempt.json").read_bytes() == marker


def test_candidate_cannot_impersonate_admitted_release(candidate_root):
    root, repository = candidate_root
    candidate.freeze(root, repository)
    assert candidate.verify(root, repository)["kind"] == "scientific-candidate-only"
    status = verify_release(root)
    assert status["status"] == "blocked"
    assert status["gates"]["ready_for_initialization"] == "blocked"
    with pytest.raises(ValueError, match="blocked before initialization"):
        initialize_release(root)
    assert not (root / "admission.json").exists()
    assert not (root / "bundle").exists()
    (root / "release.manifest.json").write_bytes(
        (root / "candidate.receipt.json").read_bytes()
    )
    with pytest.raises(ValueError, match="release"):
        candidate.verify(root, repository)


def test_candidate_detects_added_source_and_receipt_tampering(candidate_root):
    root, repository = candidate_root
    candidate.freeze(root, repository)
    added = repository / "logicmus_eval" / "new.py"
    added.write_text("# new source\n")
    with pytest.raises(ValueError, match="changed"):
        candidate.verify(root, repository)
    added.unlink()
    path = root / "candidate.receipt.json"
    receipt = json.loads(path.read_text(encoding="utf-8"))
    receipt["payload"]["release_admission"] = True
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        candidate.verify(root, repository)


def test_candidate_detects_installed_transitive_dependency_drift(
    candidate_root, monkeypatch
):
    root, repository = candidate_root
    candidate.freeze(root, repository)
    site = root.parent / "extra-site"
    metadata = site / "candidate_drift-0.0.1.dist-info"
    metadata.mkdir(parents=True)
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: candidate-drift\nVersion: 0.0.1\n"
    )
    monkeypatch.syspath_prepend(str(site))
    with pytest.raises(ValueError, match="environment changed"):
        candidate.verify(root, repository)
