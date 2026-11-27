"""Single-writer, transactional, checksummed event journal on a local filesystem."""

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from types import TracebackType
from typing import Any, BinaryIO, Self

from logicmus_eval.experiment_plan import canonical_json
from logicmus_eval.runner.preflight import digest


def atomic_json(path: Path, value: Any) -> None:
    """Reports are replaceable projections; never overwrite their old bytes in place."""
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(canonical_json(value) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RunJournal:  # pylint: disable=too-many-instance-attributes
    """Keep the lock file: unlinking a locked inode allows two writers on POSIX."""

    def __init__(
        self,
        root: Path,
        identity: str,
        *,
        create: bool = False,
        read_only: bool = False,
    ) -> None:
        self.root = root
        self.identity = identity
        self.create = create
        self.read_only = read_only
        if create and read_only:
            raise ValueError("Cannot create a read-only journal")
        self.lock: BinaryIO | None = None
        self.db: sqlite3.Connection | None = None
        self.events: list[dict[str, Any]] = []
        self.head = identity

    def __enter__(self) -> Self:
        try:
            self.lock = (self.root / "writer.lock").open(
                "rb" if self.read_only else "a+b"
            )
            self.lock.seek(0)
            if os.name == "nt":
                import msvcrt  # pylint: disable=import-outside-toplevel

                if (
                    not self.read_only
                    and (self.root / "writer.lock").stat().st_size == 0
                ):
                    self.lock.write(b"0")
                    self.lock.flush()
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl  # pylint: disable=import-outside-toplevel,import-error

                fcntl.flock(  # type: ignore[attr-defined]
                    self.lock.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,  # type: ignore[attr-defined]
                )
        except OSError as error:
            self._close()
            raise ValueError("Another writer owns this run directory") from error
        try:
            path = self.root / "journal.sqlite3"
            if not self.create and not path.is_file():
                raise ValueError("Run journal is missing; refusing to recreate it")
            if self.create and path.exists():
                raise ValueError("Run journal already exists")
            # mode=rw prevents resume from silently creating an empty database.
            self.db = sqlite3.connect(
                path
                if self.create
                else path.as_uri() + ("?mode=ro" if self.read_only else "?mode=rw"),
                uri=not self.create,
                timeout=0,
            )
            if not self.read_only:
                self.db.execute("PRAGMA journal_mode=DELETE")
                self.db.execute("PRAGMA synchronous=EXTRA")
            if self.create:
                with self.db:
                    self.db.execute("CREATE TABLE identity (value TEXT NOT NULL)")
                    self.db.execute("INSERT INTO identity VALUES (?)", (self.identity,))
                    self.db.execute(
                        "CREATE TABLE head (seq INTEGER NOT NULL, sha256 TEXT NOT NULL)"
                    )
                    self.db.execute("INSERT INTO head VALUES (0, ?)", (self.identity,))
                    self.db.execute(
                        "CREATE TABLE events (seq INTEGER PRIMARY KEY, "
                        "payload TEXT NOT NULL, sha256 TEXT NOT NULL)"
                    )
                    self.db.execute(
                        "CREATE UNIQUE INDEX finalized_job ON events "
                        "(json_extract(payload, '$.job_id')) "
                        "WHERE json_extract(payload, '$.kind') = 'finalized'"
                    )
            self._read()
            return self
        except sqlite3.DatabaseError as error:
            self._close()
            raise ValueError("Run journal is corrupt or unreadable") from error
        except BaseException:
            self._close()
            raise

    def _read(self) -> None:
        assert self.db is not None
        if self.db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("Run journal is corrupt")
        if self.db.execute("SELECT value FROM identity").fetchall() != [
            (self.identity,)
        ]:
            raise ValueError("Run journal identity is incompatible")
        self.events = []
        self.head = self.identity
        try:
            for expected, (seq, payload, checksum) in enumerate(
                self.db.execute("SELECT seq, payload, sha256 FROM events ORDER BY seq"),
                1,
            ):
                if seq != expected or digest([self.head, payload]) != checksum:
                    raise ValueError("Run journal is corrupt: sequence/checksum")
                event = json.loads(payload)
                if not isinstance(event, dict) or not isinstance(
                    event.get("kind"), str
                ):
                    raise ValueError("Run journal is corrupt: invalid event")  # noqa: TRY004
                self.events.append(event)
                self.head = checksum
            if self.db.execute("SELECT seq, sha256 FROM head").fetchall() != [
                (len(self.events), self.head)
            ]:
                raise ValueError("Run journal is corrupt: committed tail is missing")
        except (json.JSONDecodeError, TypeError) as error:
            raise ValueError("Run journal is corrupt: invalid JSON") from error

    def append(self, event: dict[str, Any]) -> None:
        if self.read_only:
            raise ValueError("Cannot append to a read-only journal")
        assert self.db is not None
        payload = canonical_json(event)
        checksum = digest([self.head, payload])
        # No in-memory acknowledgement until COMMIT succeeds. A failed commit
        # propagates; the caller must close/reopen, never continue sending HTTP.
        try:
            with self.db:
                self.db.execute(
                    "INSERT INTO events VALUES (?, ?, ?)",
                    (len(self.events) + 1, payload, checksum),
                )
                self.db.execute(
                    "UPDATE head SET seq=?, sha256=?", (len(self.events) + 1, checksum)
                )
        except sqlite3.IntegrityError as error:
            raise ValueError(
                "Duplicate finalized outcome or corrupt sequence"
            ) from error
        self.events.append(json.loads(payload))
        self.head = checksum

    def _close(self) -> None:
        if self.db is not None:
            self.db.close()
            self.db = None
        if self.lock is not None:
            # Closing releases the OS lock even after an exception. Process
            # termination also releases it; a leftover file is not ownership.
            self.lock.close()
            self.lock = None

    def __exit__(
        self,
        _kind: type[BaseException] | None,
        _value: BaseException | None,
        _trace: TracebackType | None,
    ) -> None:
        self._close()
