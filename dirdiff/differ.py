import dataclasses
import logging
import os
import stat
import tarfile
from enum import Enum
from typing import List, Optional, Tuple, Union

from dirdiff.filelib import DirectoryManager, FileManager, PathManager
from dirdiff.filelib_tar import TarDirectoryManager, TarFileLoader
from dirdiff.output import DiffOutput, StatInfo

LOGGER = logging.getLogger(__name__)

DifferPathLike = Union[str, bytes, os.PathLike, tarfile.TarFile]


class DirEntryType(Enum):
    DIRECTORY = 1
    REGULAR_FILE = 2
    OTHER = 3


def _dir_entry_type(dir_entry: os.DirEntry) -> DirEntryType:
    if dir_entry.is_dir(follow_symlinks=False):
        return DirEntryType.DIRECTORY
    if dir_entry.is_file(follow_symlinks=False):
        return DirEntryType.REGULAR_FILE
    return DirEntryType.OTHER


@dataclasses.dataclass
class DifferOptions:
    output_uid: Optional[int] = None
    output_gid: Optional[int] = None
    scrub_mtime: Optional[bool] = True

    def stats_filter(self, x: StatInfo) -> StatInfo:
        """
        Return a copy of the StatInfo object that has been adjusted based
        on the options set.
        """
        return dataclasses.replace(
            x,
            uid=self.output_uid if self.output_uid is not None else x.uid,
            gid=self.output_gid if self.output_gid is not None else x.gid,
            mtime=0 if self.scrub_mtime else x.mtime,
        )

    def stats_differ(self, x: StatInfo, y: StatInfo) -> bool:
        """
        Returns True if the data in the stat results are the same for the purposes
        of performing a diff. This takes into account the configuraiton options
        set in this object.

        Note that this does not perform any deeper diffing that may be necessary
        for some file types. In particular symlinks and regular files contents
        should be inspected as well.
        """
        x = self.stats_filter(x)
        y = self.stats_filter(y)
        if x.uid != y.uid:
            return True
        if x.gid != y.gid:
            return True
        if x.mode != y.mode:
            return True
        if stat.S_ISREG(x.mode) or stat.S_ISLNK(x.mode):
            if x.size != y.size:
                return True
        if stat.S_ISCHR(x.mode) or stat.S_ISBLK(x.mode):
            if x.rdev != y.rdev:
                return True
        return False


def _open_dir(path_dir: DifferPathLike) -> DirectoryManager:
    if isinstance(path_dir, tarfile.TarFile):
        return TarDirectoryManager(TarFileLoader(path_dir), os.path.sep)  # type: ignore
    return DirectoryManager(path_dir)


class Differ:
    def __init__(
        self,
        merged_dir: DifferPathLike,
        lower_dir: DifferPathLike,
        output: DiffOutput,
        *,
        options: Optional[DifferOptions] = None,
    ) -> None:
        self.merged_dir = merged_dir
        self.lower_dir = lower_dir
        self.output = output
        self.options = options or DifferOptions()
        self._dir_pending: List[Tuple[str, StatInfo]] = []

    def diff(self) -> None:
        with _open_dir(self.merged_dir) as merged:
            with _open_dir(self.lower_dir) as lower:
                self._diff_dirs(".", merged, lower)

    def _diff_dirs(
        self,
        archive_path: str,
        merged: DirectoryManager,
        lower: DirectoryManager,
    ) -> None:
        LOGGER.debug("Diffing dirs %s", archive_path)
        lower_map = {dir_entry.name: _dir_entry_type(dir_entry) for dir_entry in lower}

        # If stats differ write dir now. Otherwise wait until we find an actual
        # difference underneath this directory. Note that a directory should be
        # written to the output if *any* child object has changed and it should
        # be written *before* that child. Therefore we push it to `_dir_pending`
        # which must be flushed before anything else can be written.
        self._dir_pending.append((archive_path, merged.stat))
        if self.options.stats_differ(merged.stat, lower.stat):
            self._flush_pending()

        for dir_entry in merged:
            dir_entry_type = _dir_entry_type(dir_entry)
            cpath = os.path.join(archive_path, dir_entry.name)

            lower_type = lower_map.pop(dir_entry.name, None)
            if dir_entry_type == DirEntryType.DIRECTORY:
                with merged.child_dir(dir_entry.name) as merged_cdir:
                    if lower_type != DirEntryType.DIRECTORY:
                        self._insert_dir(cpath, merged_cdir)
                        continue

                    with lower.child_dir(dir_entry.name) as lower_cdir:
                        self._diff_dirs(cpath, merged_cdir, lower_cdir)
                        continue

            if dir_entry_type == DirEntryType.REGULAR_FILE:
                with merged.child_file(dir_entry.name) as merged_cfile:
                    if lower_type != DirEntryType.REGULAR_FILE:
                        self._insert_file(cpath, merged_cfile)
                        continue

                    with lower.child_file(dir_entry.name) as lower_cfile:
                        self._diff_files(cpath, merged_cfile, lower_cfile)
                        continue

            with merged.child_path(dir_entry.name) as merged_cpath:
                if lower_type != DirEntryType.OTHER:
                    self._insert_other(cpath, merged_cpath)
                    continue

                with lower.child_path(dir_entry.name) as lower_cpath:
                    self._diff_other(cpath, merged_cpath, lower_cpath)

        for name in lower_map:
            self._flush_pending()
            self.output.delete_marker(os.path.join(archive_path, name))

        # Remove ourselves from _dir_pending if we're still there. Note at this
        # point if _dir_pending isn't empty we must be at the end of it.
        if self._dir_pending:
            self._dir_pending.pop()

    def _diff_files(
        self,
        archive_path: str,
        merged: FileManager,
        lower: FileManager,
    ) -> None:
        LOGGER.debug("Diffing files %s", archive_path)
        if self.options.stats_differ(merged.stat, lower.stat):
            self._insert_file(archive_path, merged)
            return

        CHUNK_SIZE = 2**16
        differs = False
        with merged.reader() as merged_reader:
            with lower.reader() as lower_reader:
                while True:
                    merged_data = merged_reader.read(CHUNK_SIZE)
                    lower_data = lower_reader.read(CHUNK_SIZE)
                    if merged_data != lower_data:
                        differs = True
                        break
                    if not merged_data:
                        break

        if differs:
            self._insert_file(archive_path, merged)

    def _diff_other(
        self,
        archive_path: str,
        merged: PathManager,
        lower: PathManager,
    ) -> None:
        LOGGER.debug("Diffing other %s", archive_path)
        if not self.options.stats_differ(merged.stat, lower.stat):
            if not stat.S_ISLNK(merged.stat.mode):
                return
            if merged.linkname == lower.linkname:
                return
        self._insert_other(archive_path, merged)

    def _flush_pending(self) -> None:
        for archive_path, dir_stat in self._dir_pending:
            LOGGER.debug("Inserting directory metadata %s", archive_path)
            self.output.write_dir(archive_path, self.options.stats_filter(dir_stat))
        self._dir_pending.clear()

    def _insert_dir(
        self,
        archive_path: str,
        obj: DirectoryManager,
    ) -> None:
        self._flush_pending()
        LOGGER.debug("Recursively inserting directory %s", archive_path)
        self.output.write_dir(archive_path, self.options.stats_filter(obj.stat))

        for dir_entry in obj:
            cpath = os.path.join(archive_path, dir_entry.name)
            if dir_entry.is_dir(follow_symlinks=False):
                with obj.child_dir(dir_entry.name) as child_dir:
                    self._insert_dir(cpath, child_dir)
            elif dir_entry.is_file(follow_symlinks=False):
                with obj.child_file(dir_entry.name) as child_file:
                    self._insert_file(cpath, child_file)
            else:
                with obj.child_path(dir_entry.name) as child_path:
                    self._insert_other(cpath, child_path)

    def _insert_file(
        self,
        archive_path: str,
        obj: FileManager,
    ) -> None:
        self._flush_pending()
        LOGGER.debug("Inserting file %s", archive_path)
        with obj.reader() as reader:
            self.output.write_file(
                archive_path, self.options.stats_filter(obj.stat), reader
            )

    def _insert_other(
        self,
        archive_path: str,
        obj: PathManager,
    ) -> None:
        self._flush_pending()
        LOGGER.debug("Inserting other %s", archive_path)
        if stat.S_ISLNK(obj.stat.mode):
            self.output.write_symlink(
                archive_path, self.options.stats_filter(obj.stat), obj.linkname
            )
            return
        self.output.write_other(archive_path, self.options.stats_filter(obj.stat))
