"""Terminating process boundary for generated Python/Z3 programs."""

import json
import math
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pydantic import ValidationError

from logicmus_eval.enums import EvaluationErrorType
from logicmus_eval.models.evaluation import Z3ExecutionResult

CLEANUP_SECONDS = 1.0


def clean_markdown_code(code_str: str) -> str:
    cleaned = code_str.strip()
    match = re.search(r"```(?:python)?\s*(.*?)\s*```", cleaned, re.DOTALL)
    return match.group(1).strip() if match else cleaned


def _reap(process: subprocess.Popen[str]) -> None:
    """Bound cleanup separately from the execution deadline, on every exit."""
    try:
        if process.poll() is None:
            process.terminate()
        try:
            process.communicate(timeout=CLEANUP_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate(timeout=CLEANUP_SECONDS)
    finally:
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                stream.close()


class Z3CodeExecutor:
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self.timeout_seconds = timeout_seconds

    def execute(self, code_str: str, expected_rule_ids: list[str]) -> Z3ExecutionResult:
        started = time.monotonic()
        deadline = started + self.timeout_seconds

        def failure(kind: EvaluationErrorType, message: str) -> Z3ExecutionResult:
            return Z3ExecutionResult(success=False, error_type=kind, error=message)

        process: subprocess.Popen[str] | None = None
        try:
            # Windows venv python.exe is a redirector that spawns another
            # process. Own the real interpreter so terminate kills the worker,
            # not merely its launcher. Retain this environment's import paths.
            executable = sys.executable
            command = [executable, "-m", "logicmus_eval.sandbox.worker"]
            if sys.platform == "win32":
                executable = getattr(sys, "_base_executable", sys.executable)
                command = [
                    executable,
                    "-c",
                    (
                        f"import sys; sys.path[:0] = {sys.path!r}; "
                        "from logicmus_eval.sandbox.worker import main; main()"
                    ),
                ]
            # Windows communicate() writes pipe input synchronously, outside
            # its timeout. A seekable JSON input avoids a blocked pipe write
            # when startup stalls or the worker never reads the request.
            with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as request:
                json.dump(
                    {
                        "code": clean_markdown_code(code_str),
                        "expected_rule_ids": expected_rule_ids,
                        "deadline": deadline,
                    },
                    request,
                )
                request.seek(0)
                # Explicit finally below provides bounded termination; Popen's
                # context manager would add an unbounded wait on exceptions.
                process = subprocess.Popen(  # pylint: disable=consider-using-with
                    command,
                    cwd=Path(__file__).resolve().parents[2],
                    stdin=request,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    creationflags=subprocess.CREATE_NO_WINDOW
                    if sys.platform == "win32"
                    else 0,
                )
                output, _ = process.communicate(
                    timeout=max(0.0, deadline - time.monotonic())
                )
            if process.returncode != 0:
                result = failure(
                    EvaluationErrorType.Z3_WORKER_ERROR,
                    f"Z3 worker exited with status {process.returncode}",
                )
            else:
                result = Z3ExecutionResult.model_validate_json(output)
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(process.args, self.timeout_seconds)
        except subprocess.TimeoutExpired:
            result = failure(
                EvaluationErrorType.Z3_TIMEOUT,
                f"Execution timed out after {self.timeout_seconds} seconds",
            )
        except (OSError, ValueError, ValidationError) as exc:
            result = failure(
                EvaluationErrorType.Z3_WORKER_ERROR,
                f"Z3 worker protocol/startup error: {str(exc)[:8192]}",
            )
        finally:
            # Parent KeyboardInterrupt cleans up here and then propagates.
            if process is not None:
                _reap(process)
        result.execution_time = time.monotonic() - started
        return result
