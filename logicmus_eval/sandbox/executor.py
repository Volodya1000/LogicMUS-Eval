"""Terminating process boundary for generated Python/Z3 programs."""

from __future__ import annotations

import json
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError

from logicmus_eval.enums import EvaluationErrorType
from logicmus_eval.models.evaluation import Z3ExecutionResult
from logicmus_eval.sandbox.code_cleaning import clean_markdown_code
from logicmus_eval.sandbox.process_lifecycle import reap_worker, worker_command
from logicmus_eval.sandbox.protocol import WorkerRequest
from logicmus_eval.sandbox.result_building import execution_failure


class Z3CodeExecutor:
    def __init__(self, timeout_seconds: float = 5.0) -> None:
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self.timeout_seconds: float = timeout_seconds

    def execute(self, code_str: str, expected_rule_ids: list[str]) -> Z3ExecutionResult:
        started: float = time.monotonic()
        deadline: float = started + self.timeout_seconds

        process: subprocess.Popen[str] | None = None
        result: Z3ExecutionResult
        output: str
        _stderr: str | None
        request: TextIO | tempfile._TemporaryFileWrapper[str]  # pylint: disable=protected-access
        exc: OSError | ValueError
        try:
            command: list[str] = worker_command()
            # Windows communicate() writes pipe input synchronously, outside
            # its timeout. A seekable JSON input avoids a blocked pipe write
            # when startup stalls or the worker never reads the request.
            with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as request:
                payload: WorkerRequest = {
                    "code": clean_markdown_code(code_str),
                    "expected_rule_ids": expected_rule_ids,
                    "deadline": deadline,
                }
                json.dump(payload, request)
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
                output, _stderr = process.communicate(
                    timeout=max(0.0, deadline - time.monotonic())
                )
            if process.returncode != 0:
                result = execution_failure(
                    EvaluationErrorType.Z3_WORKER_ERROR,
                    f"Z3 worker exited with status {process.returncode}",
                )
            else:
                result = Z3ExecutionResult.model_validate_json(output)
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(process.args, self.timeout_seconds)
        except subprocess.TimeoutExpired:
            result = execution_failure(
                EvaluationErrorType.Z3_TIMEOUT,
                f"Execution timed out after {self.timeout_seconds} seconds",
            )
        except (OSError, ValueError, ValidationError) as exc:
            result = execution_failure(
                EvaluationErrorType.Z3_WORKER_ERROR,
                f"Z3 worker protocol/startup error: {str(exc)[:8192]}",
            )
        finally:
            # Parent KeyboardInterrupt cleans up here and then propagates.
            if process is not None:
                reap_worker(process)
        result.execution_time = time.monotonic() - started
        return result
