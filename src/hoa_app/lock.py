"""One running app per data folder – a second instance would race the first's saves."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import TracebackType
from typing import IO


class FolderInUse(Exception):
    pass


class DataFolderLock:
    """An operating-system lock on <data folder>/.lock (or another file there), held for the
    life of the process. The server holds `.lock` – the data itself; the launcher holds its own,
    so a new launch can tell the app is running even while no server is.

    The OS releases it if the process dies, so a crash never leaves a stale lock.
    """

    def __init__(self, root: Path, name: str = ".lock") -> None:
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._file: IO[str] = open(root / name, "a+", encoding="utf-8")  # noqa: SIM115
        try:
            if sys.platform == "win32":
                import msvcrt

                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), msvcrt.LK_NBLCK, 1)
            else:  # pragma: no cover – exercised on macOS and Linux
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._file.close()
            raise FolderInUse(str(root)) from None
        self._file.seek(0)
        self._file.truncate()
        self._file.write(str(os.getpid()))
        self._file.flush()

    def release(self) -> None:
        if self._file.closed:
            return
        if sys.platform == "win32":  # pragma: no branch – POSIX locks end when the file closes
            import msvcrt

            self._file.seek(0)
            msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
        self._file.close()

    def __enter__(self) -> DataFolderLock:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
