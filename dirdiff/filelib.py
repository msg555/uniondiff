import dataclasses
import functools
import os
from typing import Any, AnyStr, Iterator, Optional


def _encode(s: AnyStr) -> str:
    if isinstance(s, bytes):
        return os.fsdecode(s)
    return str(s)


@dataclasses.dataclass(frozen=True)
class StatInfo:
    """
    Dataclass representing stat metadata of a file object
    """

    mode: int
    uid: int
    gid: int
    size: int
    mtime: int
    rdev: int


class ManagerBase:
    """
    Base class for all the file object manager subclasses. Provides methods
    for accessing stat information and manages opening/closing of underlying
    file resources.

    These classes are optimized to minimize the number of syscalls and file
    system operations. In particular it handles the details of statting any
    kind of file system object and then accessing its contents (e.g. listing a
    directory or reading a file) without opening the file again.
    """

    SUPPORTS_DIR_FD = os.open in os.supports_dir_fd
    OPEN_FLAGS = os.O_RDONLY

    def __init__(self, path, *, dir_fd=None) -> None:
        self.path = _encode(path)
        self.dir_fd = dir_fd
        self.fd = -1
        self._entrances = 0

    @functools.cached_property
    def stat(self) -> StatInfo:
        """
        Compute the stat of the underlying object.

        Uses the open file descriptor if available, otherwise lstat.
        """
        st: os.stat_result
        if self.fd == -1:
            st = os.lstat(self.path, dir_fd=self.dir_fd)
        else:
            st = os.fstat(self.fd)

        return StatInfo(
            mode=st.st_mode,
            uid=st.st_uid,
            gid=st.st_gid,
            size=st.st_size,
            mtime=int(st.st_mtime),
            rdev=getattr(st, "st_rdev", 0),  # Unix only
        )

    def _open(self) -> None:
        """Open a file descriptor for the object if supported"""
        if not self.SUPPORTS_DIR_FD:
            return
        self.fd = os.open(self.path, self.OPEN_FLAGS, dir_fd=self.dir_fd)

    def __enter__(self):
        if self._entrances == 0:
            self._open()
        self._entrances += 1
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        self._entrances -= 1
        if self._entrances == 0:
            self.close()

    def close(self) -> None:
        """Close the file descriptor if open"""
        if self.fd != -1:
            os.close(self.fd)
            self.fd = -1


class FileManagerReader:
    """
    Helper class created by the FileManager.reader() method that manages
    the state of a single reader. Supports the typical file-like .read()
    method returning binary data.
    """

    HAS_PREAD = hasattr(os, "pread")

    def __init__(self, fd: int, owns: bool) -> None:
        self.fd = fd
        self.owns = owns
        self.offset = 0
        if not owns and not self.HAS_PREAD:
            raise OSError("Cannot create unowned reader without pread")

    def read(self, n: int) -> bytes:
        """Read up to `n` bytes from the file"""
        if self.HAS_PREAD:
            result = os.pread(self.fd, n, self.offset)
        else:
            assert self.owns
            result = os.read(self.fd, n)
        self.offset += len(result)
        n -= len(result)

        # Fast pass one-shot read.
        if not result or not n:
            return result

        # Slow path when we don't get as much data as we wanted.
        parts = [result]
        while n > 0:
            if self.HAS_PREAD:
                result = os.pread(self.fd, n, self.offset)
            else:
                assert self.owns
                result = os.read(self.fd, n)
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
        """Close the underlying file descriptor if it exists and we own it"""
        if self.fd != -1 and self.owns:
            os.close(self.fd)
            self.fd = -1


class FileManager(ManagerBase):
    """
    Manager subclass that enables reading of regular file objects
    """

    SUPPORTS_DIR_FD = ManagerBase.SUPPORTS_DIR_FD and (hasattr(os, "pread"))

    def reader(self) -> FileManagerReader:
        """
        Returns a new reader for this file object. Do not close this file object
        while still using this reader or you may get an IOError.
        """
        if self.fd != -1:
            return FileManagerReader(self.fd, False)
        return FileManagerReader(
            os.open(self.path, self.OPEN_FLAGS, dir_fd=self.dir_fd), True
        )


class PathManager(ManagerBase):
    """
    Manager subclass that enables accessing non-directories/non-regular files.
    """

    SUPPORTS_DIR_FD = ManagerBase.SUPPORTS_DIR_FD and (
        hasattr(os, "O_PATH") and os.readlink in os.supports_fd
    )
    OPEN_FLAGS = ManagerBase.OPEN_FLAGS | getattr(os, "O_PATH", 0)

    @functools.cached_property
    def linkname(self) -> str:
        """Returns the symlink target if this object is a symlink"""
        if self.fd != -1:
            return _encode(os.readlink(self.fd))  # type: ignore
        return _encode(os.readlink(self.path, dir_fd=self.dir_fd))


class DirectoryManager(ManagerBase):
    """
    Manager subclass that enables accessing/listing direcotires.
    """

    SUPPORTS_DIR_FD = ManagerBase.SUPPORTS_DIR_FD and (
        hasattr(os, "O_DIRECTORY") and os.scandir in os.supports_fd
    )
    OPEN_FLAGS = ManagerBase.OPEN_FLAGS | getattr(os, "O_DIRECTORY", 0)

    def __init__(self, path, *, dir_fd=None) -> None:
        super().__init__(path, dir_fd=dir_fd)
        self._scanner: Optional[Any] = None

    def __iter__(self) -> Iterator[os.DirEntry]:
        """
        Begins iteration on the directory from the beginning.

        Nesting scans of the same directory is not supported.
        """
        if self._scanner is not None:
            self._scanner.close()
        self._scanner = os.scandir(self.fd if self.fd != -1 else self.path)
        return iter(self._scanner)

    def close(self) -> None:
        """Close the scanner if open and superclass resources"""
        if self._scanner is not None:
            self._scanner.close()
            self._scanner = None
        super().close()

    def child_dir(self, name: str) -> "DirectoryManager":
        """Return a manager for a child directory object"""
        if self.fd != -1:
            return DirectoryManager(name, dir_fd=self.fd)
        return DirectoryManager(os.path.join(self.path, name))

    def child_file(self, name: str) -> FileManager:
        """Return a manager for a child regular file object"""
        if self.fd != -1:
            return FileManager(name, dir_fd=self.fd)
        return FileManager(os.path.join(self.path, name))

    def child_path(self, name: str) -> PathManager:
        """Return a manager for any other type of file object"""
        if self.fd != -1:
            return PathManager(name, dir_fd=self.fd)
        return PathManager(os.path.join(self.path, name))
