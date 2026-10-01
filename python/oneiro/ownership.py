"""Kernel-owned process leases; persistent marker files contain no owner data."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import BinaryIO


class OwnershipError(RuntimeError):
    """Another process already owns the requested resource."""


class FileLease:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._stream: BinaryIO | None = None

    def acquire(self) -> None:
        if self._stream is not None:
            raise OwnershipError("This lease is already acquired")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open("a+b")
        # Keep one lockable byte. Never delete a marker: replacing/deleting a
        # locked inode would let a new process lock a different inode.
        if self.path.stat().st_size == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            stream.close()
            raise OwnershipError("Another process owns this resource") from None
        self._stream = stream

    def release(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            stream.seek(0)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        finally:
            stream.close()

    def __enter__(self) -> FileLease:
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()
