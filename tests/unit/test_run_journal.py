import json
import os
import sqlite3
import subprocess
import sys

import pytest

from logicmus_eval.runner.journal import RunJournal


def test_one_writer_and_manifest_binding(tmp_path):
    journal = RunJournal
    with journal(tmp_path, "run-a", create=True) as first:
        first.append({"kind": "started", "job_id": "job", "attempt": 1})
        with pytest.raises(ValueError, match="writer"), journal(tmp_path, "run-a"):
            pass
    with pytest.raises(ValueError, match="identity"), journal(tmp_path, "run-b"):
        pass
    with journal(tmp_path, "run-a") as reopened:
        assert reopened.events[0]["kind"] == "started"


def test_corrupt_event_is_not_treated_as_pending(tmp_path):
    journal = RunJournal
    with journal(tmp_path, "run-a", create=True) as first:
        first.append({"kind": "started", "job_id": "job", "attempt": 1})
    with sqlite3.connect(tmp_path / "journal.sqlite3") as db:
        db.execute("UPDATE events SET payload=? WHERE seq=1", (json.dumps({"x": 1}),))
    with pytest.raises(ValueError, match="corrupt"), journal(tmp_path, "run-a"):
        pass


def test_interrupted_transaction_preserves_prior_intent(tmp_path):
    journal = RunJournal
    with journal(tmp_path, "run-a", create=True) as first:
        first.append({"kind": "started", "job_id": "job", "attempt": 1})
    child = """
import os, sqlite3, sys
db = sqlite3.connect(sys.argv[1])
db.execute('BEGIN IMMEDIATE')
db.execute('UPDATE events SET payload=? WHERE seq=1', ('{"kind":"started","job_id":"torn"}',))
os._exit(19)
"""
    result = subprocess.run(
        [sys.executable, "-c", child, str(tmp_path / "journal.sqlite3")],
        check=False,
    )
    assert result.returncode == 19
    with journal(tmp_path, "run-a") as recovered:
        assert recovered.events == [{"kind": "started", "job_id": "job", "attempt": 1}]


def test_process_death_releases_writer_lock(tmp_path):
    journal = RunJournal
    with journal(tmp_path, "run-a", create=True):
        pass
    child = """
import os, sys
from pathlib import Path
from logicmus_eval.runner.journal import RunJournal
with RunJournal(Path(sys.argv[1]), 'run-a'):
    os._exit(17)
"""
    result = subprocess.run([sys.executable, "-c", child, str(tmp_path)], check=False)
    assert result.returncode == 17
    with journal(tmp_path, "run-a") as recovered:
        assert not recovered.events


def test_second_process_cannot_write(tmp_path):
    journal = RunJournal
    child = """
import sys
from pathlib import Path
from logicmus_eval.runner.journal import RunJournal
try:
    with RunJournal(Path(sys.argv[1]), 'run-a'):
        sys.exit(3)
except ValueError as error:
    assert 'writer' in str(error)
"""
    with journal(tmp_path, "run-a", create=True):
        result = subprocess.run(
            [sys.executable, "-c", child, str(tmp_path)], check=False
        )
        assert result.returncode == 0


def test_missing_database_is_not_recreated(tmp_path):
    journal = RunJournal
    with journal(tmp_path, "run-a", create=True):
        pass
    os.unlink(tmp_path / "journal.sqlite3")
    with pytest.raises(ValueError, match="missing"), journal(tmp_path, "run-a"):
        pass


def test_duplicate_finalized_outcome_rejected_before_write(tmp_path):
    journal = RunJournal
    event = {"kind": "finalized", "job_id": "job", "outcome": {"error": "first"}}
    with journal(tmp_path, "run-a", create=True) as first:
        first.append(event)
        with pytest.raises(ValueError, match="finalized"):
            first.append({**event, "outcome": {"error": "replacement"}})
    with journal(tmp_path, "run-a") as recovered:
        assert recovered.events == [event]


def test_deleted_tail_is_corruption_not_a_pending_job(tmp_path):
    journal = RunJournal
    with journal(tmp_path, "run-a", create=True) as first:
        first.append({"kind": "started", "job_id": "one", "attempt": 1})
        first.append({"kind": "started", "job_id": "two", "attempt": 1})
    with sqlite3.connect(tmp_path / "journal.sqlite3") as db:
        db.execute("DELETE FROM events WHERE seq=2")
    with pytest.raises(ValueError, match="corrupt"), journal(tmp_path, "run-a"):
        pass
