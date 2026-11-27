"""The type checker must reject incorrect domain data, not silently accept Any."""

import subprocess
import sys


def test_mypy_checks_analysis_attributes_and_interval_fields(tmp_path):
    path = tmp_path / "analysis_contract.py"
    header = (
        "from logicmus_eval.analysis.models import (\n"
        "    AnalysisRow, CompatibilityConditions, ConfidenceInterval, AnalysisDiagnostics,\n"
        ")\n"
    )
    path.write_text(
        header
        + """
def valid(row: AnalysisRow, ci: ConfidenceInterval) -> tuple[int, str, float | None]:
    return row.dimensions.k, row.job.case_uid, ci["low"]
""",
        encoding="utf-8",
    )
    command = [
        sys.executable,
        "-m",
        "mypy",
        "--strict",
        str(path),
    ]
    good = subprocess.run(command, capture_output=True, text=True, check=False)
    assert good.returncode == 0, good.stdout + good.stderr
    path.write_text(
        header
        + """
def invalid(row: AnalysisRow, ci: ConfidenceInterval, conditions: CompatibilityConditions) -> None:
    row.job.case_uid = 42
    ci["low"] = "unknown"
    ci["status"] = "finished"
    conditions.runtime.python = 123
    row["family_id"]
    AnalysisDiagnostics(mode="unknown")
""",
        encoding="utf-8",
    )
    bad = subprocess.run(command, capture_output=True, text=True, check=False)
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert bad.stdout.count("error:") == 6, bad.stdout
    assert "[typeddict-item]" in bad.stdout
    assert "[assignment]" in bad.stdout
    assert "[index]" in bad.stdout
    assert "[arg-type]" in bad.stdout
