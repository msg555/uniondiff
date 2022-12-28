import dataclasses
import logging
import os
import stat
from enum import Enum
from typing import List, Optional, Tuple

from dirdiff.filelib import DirectoryManager, FileManager, PathManager
from dirdiff.output import DiffOutput, StatInfo

LOGGER = logging.getLogger(__name__)


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

    def stats_filter(self, x: os.stat_result) -> StatInfo:
        """
        Return a copy of the stat_result object that has been adjusted based
        on the options set.
        """
        return StatInfo(
            st_mode=x.st_mode,
            st_uid=self.output_uid if self.output_uid is not None else x.st_uid,
            st_gid=self.output_gid if self.output_gid is not None else x.st_gid,
            st_size=x.st_size,
            st_mtime=0 if self.scrub_mtime else int(x.st_mtime),
            st_rdev=x.st_rdev,
        )

    def stats_differ(self, st_x: os.stat_result, st_y: os.stat_result) -> bool:
        """
        Returns True if the data in the stat results are the same for the purposes
        of performing a diff. This takes into account the configuraiton options
        set in this object.

        Note that this does not perform any deeper diffing that may be necessary
        for some file types. In particular symlinks and regular files contents
        should be inspected as well.
        """
        x = self.stats_filter(st_x)
        y = self.stats_filter(st_y)
        if x.st_uid != y.st_uid:
            return True
        if x.st_gid != y.st_gid:
            return True
        if x.st_mode != y.st_mode:
            return True
        if stat.S_ISREG(x.st_mode) or stat.S_ISLNK(x.st_mode):
            if x.st_size != y.st_size:
                return True
        if stat.S_ISCHR(x.st_mode) or stat.S_ISBLK(x.st_mode):
            if x.st_rdev != y.st_rdev:
                return True
        return False


class Differ:
    def __init__(
        self,
        upper_path,
        merged_path,
        output: DiffOutput,
        *,
        options: Optional[DifferOptions] = None,
    ) -> None:
        self.upper_path = upper_path
        self.merged_path = merged_path
        self.output = output
        self.options = options or DifferOptions()
        self._dir_pending: List[Tuple[str, os.stat_result]] = []

    def diff(self) -> None:
        with DirectoryManager(self.upper_path) as upper:
            with DirectoryManager(self.merged_path) as merged:
                self._diff_dirs(".", upper, merged)

    def _diff_dirs(
        self,
        archive_path: str,
        upper: DirectoryManager,
        merged: DirectoryManager,
    ) -> None:
        upper_map = {dir_entry.name: _dir_entry_type(dir_entry) for dir_entry in upper}

        # If stats differ write dir now. Otherwise wait until we find an actual
        # difference underneath this directory. Note that a directory should be
        # written to the output if *any* child object has changed and it should
        # be written *before* that child. Therefore we push it to `_dir_pending`
        # which must be flushed before anything else can be written.
        self._dir_pending.append((archive_path, merged.stat))
        if self.options.stats_differ(upper.stat, merged.stat):
            self._flush_pending()

        for dir_entry in merged:
            dir_entry_type = _dir_entry_type(dir_entry)
            cpath = os.path.join(archive_path, dir_entry.name)

            upper_type = upper_map.pop(dir_entry.name, None)
            if dir_entry_type == DirEntryType.DIRECTORY:
                with merged.child_dir(dir_entry.name) as merged_cdir:
                    if upper_type != DirEntryType.DIRECTORY:
                        self._insert_dir(cpath, merged_cdir)
                        continue

                    with upper.child_dir(dir_entry.name) as upper_cdir:
                        self._diff_dirs(cpath, upper_cdir, merged_cdir)
                        continue

            if dir_entry_type == DirEntryType.REGULAR_FILE:
                with merged.child_file(dir_entry.name) as merged_cfile:
                    if upper_type != DirEntryType.REGULAR_FILE:
                        self._insert_file(cpath, merged_cfile)
                        continue

                    with upper.child_file(dir_entry.name) as upper_cfile:
                        self._diff_files(cpath, upper_cfile, merged_cfile)
                        continue

            with merged.child_path(dir_entry.name) as merged_cpath:
                if upper_type != DirEntryType.OTHER:
                    self._insert_other(cpath, merged_cpath)
                    continue

                with upper.child_path(dir_entry.name) as upper_cpath:
                    self._diff_other(cpath, upper_cpath, merged_cpath)

        for name in upper_map:
            self._flush_pending()
            self.output.delete_marker(os.path.join(archive_path, name))

        # Remove ourselves from _dir_pending if we're still there. Note at this
        # point if _dir_pending isn't empty we must be at the end of it.
        if self._dir_pending:
            self._dir_pending.pop()

    def _diff_files(
        self,
        archive_path: str,
        upper: FileManager,
        merged: FileManager,
    ) -> None:
        if self.options.stats_differ(upper.stat, merged.stat):
            self._insert_file(archive_path, merged)
            return

        CHUNK_SIZE = 2**16
        differs = False
        with upper.reader() as upper_reader:
            with merged.reader() as merged_reader:
                while True:
                    upper_data = upper_reader.read(CHUNK_SIZE)
                    merged_data = merged_reader.read(CHUNK_SIZE)
                    if upper_data != merged_data:
                        differs = True
                        break
                    if not upper_data:
                        break

        if differs:
            self._insert_file(archive_path, merged)

    def _diff_other(
        self,
        archive_path: str,
        upper: PathManager,
        merged: PathManager,
    ) -> None:
        if not self.options.stats_differ(upper.stat, merged.stat):
            if not stat.S_ISLNK(merged.stat.st_mode):
                return
            if upper.linkname == merged.linkname:
                return
        self._insert_other(archive_path, merged)

    def _flush_pending(self) -> None:
        for archive_path, dir_stat in self._dir_pending:
            self.output.write_dir(archive_path, self.options.stats_filter(dir_stat))
        self._dir_pending.clear()

    def _insert_dir(
        self,
        archive_path: str,
        obj: DirectoryManager,
    ) -> None:
        self._flush_pending()
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
        if stat.S_ISLNK(obj.stat.st_mode):
            self.output.write_symlink(
                archive_path, self.options.stats_filter(obj.stat), obj.linkname
            )
            return
        self.output.write_other(archive_path, self.options.stats_filter(obj.stat))
