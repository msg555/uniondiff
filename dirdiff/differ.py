import dataclasses
import logging
import os
import stat
import sys
import tarfile
from contextlib import ExitStack
from enum import Enum
from typing import List, Optional, Tuple, Union

from dirdiff.exceptions import (
    DirDiffException,
    DirDiffInputException,
    DirDiffIOException,
    DirDiffOutputException,
)
from dirdiff.filelib import DirectoryManager, FileManager, PathManager
from dirdiff.filelib_tar import TarDirectoryManager, TarFileLoader
from dirdiff.output import DiffOutput, StatInfo

LOGGER = logging.getLogger(__name__)

DifferPathLike = Union[str, bytes, os.PathLike, tarfile.TarFile]

IOErrors = (OSError, tarfile.TarError, DirDiffIOException)

FAILED_STAT = StatInfo(
    mode=0o777,
    uid=0,
    gid=0,
    size=0,
    mtime=0,
    rdev=0,
)

OPERAND_MERGED = "merged"
OPERAND_LOWER = "lower"


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
    scrub_mtime: bool = True
    input_error_strict: bool = True
    output_error_strict: bool = True

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


def _new_stack(func):
    def _invoke(differ: "Differ", *args, **kwargs):
        prev_stack = differ._cur_stack
        with ExitStack() as differ._cur_stack:
            try:
                return func(differ, *args, **kwargs)
            finally:
                differ._cur_stack = prev_stack

    return _invoke


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
        self.options = DifferOptions() if options is None else options
        self._dir_pending: List[Tuple[str, StatInfo]] = []
        self._cur_stack = ExitStack()

    @_new_stack
    def diff(self) -> None:
        try:
            merged = self._cur_stack.enter_context(_open_dir(self.merged_dir))
        except IOErrors as exc:
            raise DirDiffException(
                f"Failed to open merged path {self.merged_dir!r}: {exc}"
            ) from exc
        try:
            lower = self._cur_stack.enter_context(_open_dir(self.lower_dir))
        except IOErrors as exc:
            raise DirDiffException(
                f"Failed to open lower path {self.lower_dir!r}: {exc}"
            ) from exc
        self._diff_dirs(".", merged, lower)

    def _input_error(self, operand: str, path: str, verb: str) -> None:
        _, exc, _ = sys.exc_info()
        if exc is not None:
            msg = f"error {verb} path={path!r} of {operand}: {exc}"
        else:
            msg = f"error {verb} path={path!r} of {operand}"
        if self.options.input_error_strict:
            raise DirDiffInputException(msg) from exc
        LOGGER.warning("ignoring %s", msg)

    def _output_error(self, path: str, verb: str) -> None:
        _, exc, _ = sys.exc_info()
        if exc is not None:
            msg = f"error {verb} path={path!r}: {exc}"
        else:
            msg = f"error {verb} path={path!r}"
        if self.options.output_error_strict:
            raise DirDiffOutputException(msg) from exc
        LOGGER.warning("ignoring %s", msg)

    def _input_error_merged(self, path: str, verb: str) -> None:
        self._input_error(OPERAND_MERGED, path, verb)

    def _input_error_lower(self, path: str, verb: str) -> None:
        self._input_error(OPERAND_LOWER, path, verb)

    @_new_stack
    def _diff_dirs(
        self,
        archive_path: str,
        merged: DirectoryManager,
        lower: DirectoryManager,
    ) -> None:
        stack = self._cur_stack
        LOGGER.debug("Diffing dirs %s", archive_path)

        lower_map = {}
        lower_stat = FAILED_STAT
        try:
            stack.enter_context(lower)
            lower_map = {
                dir_entry.name: _dir_entry_type(dir_entry) for dir_entry in lower
            }
            lower_stat = lower.stat
        except IOErrors:
            self._input_error_lower(archive_path, "listing")

        merged_entries = []
        merged_stat = FAILED_STAT
        try:
            stack.enter_context(merged)
            merged_entries = list(merged)
            merged_stat = merged.stat
        except IOErrors:
            self._input_error_merged(archive_path, "listing")
            LOGGER.warning("treating %s as empty", archive_path)

        # If stats differ write dir now. Otherwise wait until we find an actual
        # difference underneath this directory. Note that a directory should be
        # written to the output if *any* child object has changed and it should
        # be written *before* that child. Therefore we push it to `_dir_pending`
        # which must be flushed before anything else can be written.
        self._dir_pending.append((archive_path, merged_stat))
        if self.options.stats_differ(merged_stat, lower_stat):
            self._flush_pending()

        for dir_entry in merged_entries:
            dir_entry_type = _dir_entry_type(dir_entry)
            cpath = os.path.join(archive_path, dir_entry.name)

            lower_type = lower_map.pop(dir_entry.name, None)
            if dir_entry_type == DirEntryType.DIRECTORY:
                merged_cdir = merged.child_dir(dir_entry.name)
                if lower_type != DirEntryType.DIRECTORY:
                    self._insert_dir(cpath, merged_cdir)
                    continue

                lower_cdir = lower.child_dir(dir_entry.name)
                self._diff_dirs(cpath, merged_cdir, lower_cdir)
                continue

            if dir_entry_type == DirEntryType.REGULAR_FILE:
                merged_cfile = merged.child_file(dir_entry.name)
                if lower_type != DirEntryType.REGULAR_FILE:
                    self._insert_file(cpath, merged_cfile)
                    continue

                lower_cfile = lower.child_file(dir_entry.name)
                self._diff_files(cpath, merged_cfile, lower_cfile)
                continue

            merged_cpath = merged.child_path(dir_entry.name)
            if lower_type != DirEntryType.OTHER:
                self._insert_other(cpath, merged_cpath)
                continue

            lower_cpath = lower.child_path(dir_entry.name)
            self._diff_other(cpath, merged_cpath, lower_cpath)

        for name in lower_map:
            self._flush_pending()
            try:
                self.output.delete_marker(os.path.join(archive_path, name))
            except IOErrors:
                self._output_error(archive_path, "creating delete marker")

        # Remove ourselves from _dir_pending if we're still there. Note at this
        # point if _dir_pending isn't empty we must be at the end of it.
        if self._dir_pending:
            self._dir_pending.pop()

    @_new_stack
    def _diff_files(
        self,
        archive_path: str,
        merged: FileManager,
        lower: FileManager,
    ) -> None:
        stack = self._cur_stack
        LOGGER.debug("Diffing files %s", archive_path)

        try:
            stack.enter_context(merged)
            merged_stat = merged.stat
        except IOErrors:
            self._input_error_merged(archive_path, "accessing")
            LOGGER.warning("skipping file %s", archive_path)
            return

        lower_stat = FAILED_STAT
        try:
            stack.enter_context(lower)
            lower_stat = lower.stat
        except IOErrors:
            self._input_error_lower(archive_path, "accessing")

        if self.options.stats_differ(merged_stat, lower_stat):
            self._insert_file(archive_path, merged)
            return

        CHUNK_SIZE = 2**16
        differs = False
        try:
            merged_reader = stack.enter_context(merged.reader())
        except IOErrors:
            self._input_error_merged(archive_path, "opening")
            LOGGER.warning("skipping file %s", archive_path)
            return

        try:
            lower_reader = stack.enter_context(lower.reader())
        except IOErrors:
            self._input_error_lower(archive_path, "opening")

        while True:
            try:
                merged_data = merged_reader.read(CHUNK_SIZE)
            except IOErrors:
                self._input_error_merged(archive_path, "reading")
                LOGGER.warning("skipping file %s", archive_path)
                return

            try:
                lower_data = lower_reader.read(CHUNK_SIZE)
            except IOErrors:
                self._input_error_lower(archive_path, "reading")
                differs = True
                break

            if merged_data != lower_data:
                differs = True
                break
            if not merged_data:
                break

        if differs:
            self._insert_file(archive_path, merged)

    @_new_stack
    def _diff_other(
        self,
        archive_path: str,
        merged: PathManager,
        lower: PathManager,
    ) -> None:
        stack = self._cur_stack
        LOGGER.debug("Diffing other %s", archive_path)

        try:
            stack.enter_context(merged)
            merged_stat = merged.stat
            merged_linkname = merged.linkname if stat.S_ISLNK(merged_stat.mode) else ""
        except IOErrors:
            self._input_error_merged(archive_path, "accessing")
            LOGGER.warning("skipping object %s", archive_path)
            return

        lower_stat = FAILED_STAT
        lower_linkname = ""
        try:
            stack.enter_context(lower)
            lower_stat = lower.stat
            lower_linkname = lower.linkname if stat.S_ISLNK(lower_stat.mode) else ""
        except IOErrors:
            self._input_error_lower(archive_path, "accessing")

        if not self.options.stats_differ(merged_stat, lower_stat):
            if not stat.S_ISLNK(merged_stat.mode):
                return
            if merged_linkname == lower_linkname:
                return

        self._insert_other(archive_path, merged)

    def _flush_pending(self) -> None:
        for archive_path, dir_stat in self._dir_pending:
            LOGGER.debug("Inserting directory metadata %s", archive_path)
            try:
                self.output.write_dir(archive_path, self.options.stats_filter(dir_stat))
            except IOErrors:
                self._output_error(archive_path, "creating dir")
        self._dir_pending.clear()

    @_new_stack
    def _insert_dir(
        self,
        archive_path: str,
        obj: DirectoryManager,
    ) -> None:
        stack = self._cur_stack
        self._flush_pending()
        LOGGER.debug("Recursively inserting directory %s", archive_path)

        obj_stat = FAILED_STAT
        dir_entries = []
        try:
            stack.enter_context(obj)
            obj_stat = obj.stat
            dir_entries = list(obj)
        except IOErrors:
            self._input_error_merged(archive_path, "listing")

        try:
            self.output.write_dir(archive_path, self.options.stats_filter(obj_stat))
        except IOErrors:
            self._output_error(archive_path, "creating dir")
        for dir_entry in dir_entries:
            cpath = os.path.join(archive_path, dir_entry.name)
            if dir_entry.is_dir(follow_symlinks=False):
                self._insert_dir(cpath, obj.child_dir(dir_entry.name))
            elif dir_entry.is_file(follow_symlinks=False):
                self._insert_file(cpath, obj.child_file(dir_entry.name))
            else:
                self._insert_other(cpath, obj.child_path(dir_entry.name))

    @_new_stack
    def _insert_file(
        self,
        archive_path: str,
        obj: FileManager,
    ) -> None:
        stack = self._cur_stack
        self._flush_pending()
        LOGGER.debug("Inserting file %s", archive_path)

        try:
            stack.enter_context(obj)
            obj_stat = obj.stat
            reader = stack.enter_context(obj.reader())
        except IOErrors:
            self._input_error_merged(archive_path, "opening")
            LOGGER.warning("skipping file %s", archive_path)
            return

        try:
            self.output.write_file(
                archive_path, self.options.stats_filter(obj_stat), reader
            )
        except IOErrors:
            self._output_error(archive_path, "writing file")

    @_new_stack
    def _insert_other(
        self,
        archive_path: str,
        obj: PathManager,
    ) -> None:
        stack = self._cur_stack
        self._flush_pending()
        LOGGER.debug("Inserting other %s", archive_path)

        try:
            stack.enter_context(obj)
            obj_stat = obj.stat
            obj_linkname = obj.linkname if stat.S_ISLNK(obj_stat.mode) else ""
        except IOErrors:
            self._input_error_merged(archive_path, "accessing")
            LOGGER.warning("skipping object %s", archive_path)
            return

        if stat.S_ISLNK(obj_stat.mode):
            try:
                self.output.write_symlink(
                    archive_path, self.options.stats_filter(obj_stat), obj_linkname
                )
            except IOErrors:
                self._output_error(archive_path, "writing symlink")
            return
        try:
            self.output.write_other(archive_path, self.options.stats_filter(obj_stat))
        except IOErrors:
            self._output_error(archive_path, "writing other")
