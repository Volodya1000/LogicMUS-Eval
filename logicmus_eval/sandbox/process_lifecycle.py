"""Interpreter launch configuration and bounded worker cleanup."""

import subprocess
import sys
from typing import IO

from logicmus_eval.sandbox.limits import CLEANUP_SECONDS


def reap_worker(process: subprocess.Popen[str]) -> None:
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
        stream: IO[str] | None
        for stream in (process.stdin, process.stdout):
            if stream is not None:
                stream.close()


def worker_command() -> list[str]:
    # Windows venv python.exe is a redirector that spawns another
    # process. Own the real interpreter so terminate kills the worker,
    # not merely its launcher. Retain this environment's import paths.
    executable: str = sys.executable
    command: list[str] = [executable, "-m", "logicmus_eval.sandbox.worker"]
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
    return command
