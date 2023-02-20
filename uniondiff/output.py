import abc
import logging
import stat

from uniondiff.filelib import StatInfo
from uniondiff.osshim import major, minor

LOGGER = logging.getLogger(__name__)


class OutputBackend(metaclass=abc.ABCMeta):
    """
    Interface used to write file objects to an arbitrary backend.
    """

    @abc.abstractmethod
    def write_dir(self, path: str, st: StatInfo) -> None:
        """Write a directory entry"""

    @abc.abstractmethod
    def write_file(self, path: str, st: StatInfo, reader) -> None:
        """Write a file entry"""

    @abc.abstractmethod
    def write_symlink(self, path: str, st: StatInfo, linkname: str) -> None:
        """Write a symlink"""

    @abc.abstractmethod
    def write_other(self, path: str, st: StatInfo) -> None:
        """Write any other type of a file. Use st.mode to further differentiate"""


class DiffOutput(OutputBackend):
    """
    Interface used to write diff output to an arbitrary backend. Adds the
    `delete_marker` method to the existing OutputBackend interface.
    """

    @abc.abstractmethod
    def delete_marker(self, path: str) -> None:
        """Create a deletion marker at `path`"""


class DiffOutputForwarding(DiffOutput):  # pylint: disable=abstract-method
    """
    DiffOutput partial implementation that forwards all of the OutputBackend
    methods to a chained backend. A subclass needs to only implement
    `delete_marker` to complete the implementation.
    """

    def __init__(self, backend: OutputBackend) -> None:
        self.backend = backend

    def write_dir(self, path: str, st: StatInfo) -> None:
        self.backend.write_dir(path, st)

    def write_file(self, path: str, st: StatInfo, reader) -> None:
        self.backend.write_file(path, st, reader)

    def write_symlink(self, path: str, st: StatInfo, linkname: str) -> None:
        self.backend.write_symlink(path, st, linkname)

    def write_other(self, path: str, st: StatInfo) -> None:
        self.backend.write_other(path, st)


class DiffOutputDryRun(DiffOutput):
    """
    Simple DiffOutput concrete implementation that simply logs all write
    and deletion marker calls.
    """

    def delete_marker(self, path: str) -> None:
        print(f"delete {repr(path)}")

    @staticmethod
    def _desc(path: str, st: StatInfo) -> str:
        return (
            f"{repr(path)} mode={(stat.S_IMODE(st.mode)):03o} owner={st.uid}:{st.gid}"
        )

    def write_dir(self, path: str, st: StatInfo) -> None:
        print(f"dir {self._desc(path, st)}")

    def write_file(self, path: str, st: StatInfo, reader) -> None:
        print(f"file {self._desc(path, st)}")
        assert reader

    def write_symlink(self, path: str, st: StatInfo, linkname: str) -> None:
        print(f"symlink {self._desc(path, st)} target={repr(linkname)}")

    def write_other(self, path: str, st: StatInfo) -> None:
        other_formats = {
            stat.S_IFSOCK: "sock",
            stat.S_IFBLK: "block",
            stat.S_IFCHR: "char",
            stat.S_IFIFO: "fifo",
            stat.S_IFDOOR: "door",
            stat.S_IFPORT: "port",
            stat.S_IFWHT: "whiteout",
        }
        fmt = stat.S_IFMT(st.mode)
        fmt_name = other_formats.get(fmt)
        if fmt_name is None:
            print(f"other {self._desc(path, st)} type={fmt}")
        elif fmt_name in ("block", "char"):
            print(
                f"{fmt_name} {self._desc(path, st)} dev={major(st.rdev)}:{minor(st.rdev)}"
            )
        else:
            print(f"{fmt_name} {self._desc(path, st)}")
