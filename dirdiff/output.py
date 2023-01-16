import abc
import logging
import stat

from dirdiff.filelib import StatInfo
from dirdiff.osshim import major, minor

LOGGER = logging.getLogger(__name__)


class OutputBackend(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def write_dir(self, path: str, st: StatInfo) -> None:
        pass

    @abc.abstractmethod
    def write_file(self, path: str, st: StatInfo, reader) -> None:
        pass

    @abc.abstractmethod
    def write_symlink(self, path: str, st: StatInfo, linkname: str) -> None:
        pass

    @abc.abstractmethod
    def write_other(self, path: str, st: StatInfo) -> None:
        pass


class DiffOutput(OutputBackend):
    @abc.abstractmethod
    def delete_marker(self, path: str) -> None:
        pass


class DiffOutputForwarding(DiffOutput):  # pylint: disable=abstract-method
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
