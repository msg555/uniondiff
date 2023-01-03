import collections
import contextlib
import functools
import os
import stat
import tarfile
from tarfile import TarFile, TarInfo
from typing import Iterator

from dirdiff.filelib import StatInfo

_MODE_MAPPING = {
    tarfile.REGTYPE: stat.S_IFREG,
    tarfile.SYMTYPE: stat.S_IFLNK,
    tarfile.DIRTYPE: stat.S_IFDIR,
    tarfile.FIFOTYPE: stat.S_IFIFO,
    tarfile.CHRTYPE: stat.S_IFCHR,
    tarfile.BLKTYPE: stat.S_IFBLK,
}


def _norm_name(name: str) -> str:
    return os.path.normpath(os.path.join(os.path.sep, name))


class TarFileLoader:
    def __init__(self, tf: TarFile) -> None:
        self.tf = tf
        self.children = collections.defaultdict(list)
        self.info = {}
        for ti in tf.getmembers():
            path = _norm_name(ti.name)
            parent_path, filename = os.path.split(path)
            if filename:
                self.children[parent_path].append((filename, ti))
            self.info[path] = ti


class TarManagerBase:
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
        mode = _MODE_MAPPING.get(self.ti.type)
        if mode is None:
            raise OSError("Unsupported tar member type")
        mode |= self.ti.mode
        rdev = os.makedev(
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
        pass


class TarFileManager(TarManagerBase):
    def reader(self):
        return contextlib.nullcontext(self.loader.tf.extractfile(self.ti))


class TarPathManager(TarManagerBase):
    @functools.cached_property
    def linkname(self) -> str:
        return self.ti.linkname


class TarDirEntry:
    def __init__(self, filename: str, ti: TarInfo) -> None:
        self.ti = ti
        self.name = filename

    def is_dir(self, *, follow_symlinks=False) -> bool:
        assert not follow_symlinks
        return self.ti.isdir()

    def is_file(self, *, follow_symlinks=False) -> bool:
        assert not follow_symlinks
        return self.ti.isfile()


class TarDirectoryManager(TarManagerBase):
    def __iter__(self) -> Iterator[TarDirEntry]:
        return (TarDirEntry(filename, ti) for filename, ti in self.children)

    def close(self) -> None:
        pass

    def child_dir(self, name: str) -> "TarDirectoryManager":
        return TarDirectoryManager(self.loader, os.path.join(self.name, name))

    def child_file(self, name: str) -> TarFileManager:
        return TarFileManager(self.loader, os.path.join(self.name, name))

    def child_path(self, name: str) -> TarPathManager:
        return TarPathManager(self.loader, os.path.join(self.name, name))
