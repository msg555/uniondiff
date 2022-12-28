import functools
import os
from typing import Any, AnyStr, Iterator, Optional


def _encode(s: AnyStr) -> str:
    if isinstance(s, bytes):
        return os.fsdecode(s)
    return str(s)


class ManagerBase:
    SUPPORTS_DIR_FD = os.open in os.supports_dir_fd
    OPEN_FLAGS = os.O_RDONLY

    def __init__(self, path, *, dir_fd=None) -> None:
        self.path = _encode(path)
        self.dir_fd = dir_fd
        self.fd = -1

    @functools.cached_property
    def stat(self) -> os.stat_result:
        if self.fd == -1:
            return os.lstat(self.path, dir_fd=self.dir_fd)
        return os.fstat(self.fd)

    def _open(self) -> None:
        if not self.SUPPORTS_DIR_FD:
            return
        self.fd = os.open(self.path, self.OPEN_FLAGS, dir_fd=self.dir_fd)

    def __enter__(self):
        self._open()
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        if self.fd != -1:
            os.close(self.fd)
            self.fd = -1


class FileManagerReader:
    def __init__(self, fd: int, owns: bool) -> None:
        self.fd = fd
        self.owns = owns
        self.offset = 0

    def read(self, n=2**16) -> bytes:
        result = os.pread(self.fd, n, self.offset)
        self.offset += len(result)
        n -= len(result)

        # Fast pass one-shot read.
        if not result or not n:
            return result

        # Slow path when we don't get as much data as we wanted.
        parts = [result]
        while n > 0:
            result = os.pread(self.fd, n, self.offset)
            self.offset += len(result)
            n -= len(result)
            if not result:
                break
            parts.append(result)

        return b"".join(parts)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        if self.fd != -1 and self.owns:
            os.close(self.fd)
            self.fd = -1


class FileManager(ManagerBase):
    def reader(self) -> FileManagerReader:
        if self.fd != -1:
            return FileManagerReader(self.fd, False)
        return FileManagerReader(
            os.open(self.path, self.OPEN_FLAGS, dir_fd=self.dir_fd), True
        )


class PathManager(ManagerBase):
    SUPPORTS_DIR_FD = ManagerBase.SUPPORTS_DIR_FD and (
        hasattr(os, "O_PATH") and os.readlink in os.supports_fd
    )
    OPEN_FLAGS = ManagerBase.OPEN_FLAGS | getattr(os, "O_PATH", 0)

    @functools.cached_property
    def linkname(self) -> str:
        if self.fd != -1:
            return _encode(os.readlink(self.fd))  # type: ignore
        return _encode(os.readlink(self.path, dir_fd=self.dir_fd))


class DirectoryManager(ManagerBase):
    SUPPORTS_DIR_FD = ManagerBase.SUPPORTS_DIR_FD and (
        hasattr(os, "O_DIRECTORY") and os.scandir in os.supports_fd
    )
    OPEN_FLAGS = ManagerBase.OPEN_FLAGS | getattr(os, "O_DIRECTORY", 0)

    def __init__(self, path, *, dir_fd=None) -> None:
        super().__init__(path, dir_fd=dir_fd)
        self._scanner: Optional[Any] = None

    def __iter__(self) -> Iterator[os.DirEntry]:
        if self._scanner is not None:
            self._scanner.close()
        self._scanner = os.scandir(self.fd if self.fd != -1 else self.path)
        return iter(self._scanner)

    def close(self) -> None:
        if self._scanner is not None:
            self._scanner.close()
            self._scanner = None
        super().close()

    def child_dir(self, name: str) -> "DirectoryManager":
        if self.fd != -1:
            return DirectoryManager(name, dir_fd=self.fd)
        return DirectoryManager(os.path.join(self.path, name))

    def child_file(self, name: str) -> FileManager:
        if self.fd != -1:
            return FileManager(name, dir_fd=self.fd)
        return FileManager(os.path.join(self.path, name))

    def child_path(self, name: str) -> PathManager:
        if self.fd != -1:
            return PathManager(name, dir_fd=self.fd)
        return PathManager(os.path.join(self.path, name))
