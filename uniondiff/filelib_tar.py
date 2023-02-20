import collections
import contextlib
import functools
import stat
import tarfile
from tarfile import TarFile, TarInfo
from typing import Iterator

from uniondiff.filelib import StatInfo
from uniondiff.osshim import makedev, posix_join, posix_norm, posix_split

_MODE_MAPPING = {
    tarfile.REGTYPE: stat.S_IFREG,
    tarfile.SYMTYPE: stat.S_IFLNK,
    tarfile.DIRTYPE: stat.S_IFDIR,
    tarfile.FIFOTYPE: stat.S_IFIFO,
    tarfile.CHRTYPE: stat.S_IFCHR,
    tarfile.BLKTYPE: stat.S_IFBLK,
}


def _norm_name(name: str) -> str:
    """
    Return a normalized form of a name from a tar archive that always starts
    with a leading '/'.
    """
    return posix_norm(posix_join("/", name))


class TarFileLoader:
    """
    Organizes tar archive metadata to support the file system operations
    needed by the filelib module interface.

    Note: the passed tarfile object must support random access to be used
    by this module.
    """

    MISSING_DIRECTORY_TARINFO = TarInfo()

    def __init__(self, tf: TarFile) -> None:
        self.tf = tf
        self.children = collections.defaultdict(list)
        self.info = {}
        for ti in tf.getmembers():
            path = _norm_name(ti.name)
            parent_path, filename = posix_split(path)
            self.info[path] = ti

            while filename:
                self.children[parent_path].append((filename, ti))
                if parent_path in self.info:
                    break
                self.info[parent_path] = self.MISSING_DIRECTORY_TARINFO
                parent_path, filename = posix_split(parent_path)


class TarManagerBase:
    """
    An API mirroring the interface of the filelib module but instead reading
    from a tar archive.
    """

    def __init__(self, loader: TarFileLoader, name: str) -> None:
        self.loader = loader
        self.name = name
        try:
            self.ti = loader.info[name]
        except KeyError:
            # pylint: disable=raise-missing-from
            raise FileNotFoundError(f"Object {name} does not exist in archive")
        self.children = loader.children.get(name, [])

    @functools.cached_property
    def stat(self) -> StatInfo:
        """
        Return stat information for this tar archive entry.
        """
        mode = _MODE_MAPPING.get(self.ti.type)
        if mode is None:
            raise OSError("Unsupported tar member type")
        mode |= self.ti.mode
        rdev = makedev(
            getattr(self.ti, "devmajor", 0),
            getattr(self.ti, "devminor", 0),
        )
        return StatInfo(
            mode=mode,
            uid=self.ti.uid,
            gid=self.ti.gid,
            size=self.ti.size,
            mtime=self.ti.mtime,
            rdev=rdev,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb) -> None:
        pass

    def close(self) -> None:
        """Tar-based manager does not have open resources to close"""


class TarFileManager(TarManagerBase):
    """Like filelib.FileManager for tar archives"""

    def reader(self):
        """Return a file-like interface supporting read()"""
        return contextlib.nullcontext(self.loader.tf.extractfile(self.ti))


class TarPathManager(TarManagerBase):
    """Like filelib.PathManager for tar archives"""

    @functools.cached_property
    def linkname(self) -> str:
        """Return the symlink target if a symlink"""
        return self.ti.linkname


class TarDirEntry:
    """
    Class emulating the os.DirEntry interface for use with
    iterating over tar directories.
    """

    def __init__(self, filename: str, ti: TarInfo) -> None:
        self.ti = ti
        self.name = filename

    def is_dir(self, *, follow_symlinks=False) -> bool:
        """Returns true if the entry is a directory"""
        assert not follow_symlinks
        return self.ti.isdir()

    def is_file(self, *, follow_symlinks=False) -> bool:
        """Returns true if the entry is a regular file"""
        assert not follow_symlinks
        return self.ti.isfile()


class TarDirectoryManager(TarManagerBase):
    """Like filelib.DirectoryManager for tar archives"""

    def __iter__(self) -> Iterator[TarDirEntry]:
        return (TarDirEntry(filename, ti) for filename, ti in self.children)

    def exists_in_archive(self) -> bool:
        """
        Returns true if this directory node actually exists in the archive
        or was synthesized because it has children present in the archive.
        """
        return self.ti is not self.loader.MISSING_DIRECTORY_TARINFO

    def child_dir(self, name: str) -> "TarDirectoryManager":
        """Return a manager for a child directory object"""
        return TarDirectoryManager(self.loader, posix_join(self.name, name))

    def child_file(self, name: str) -> TarFileManager:
        """Return a manager for a child regular file object"""
        return TarFileManager(self.loader, posix_join(self.name, name))

    def child_path(self, name: str) -> TarPathManager:
        """Return a manager for any other type of file object"""
        return TarPathManager(self.loader, posix_join(self.name, name))
