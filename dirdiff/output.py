import abc
import dataclasses
import logging

LOGGER = logging.getLogger(__name__)


@dataclasses.dataclass
class StatInfo:
    st_mode: int
    st_uid: int
    st_gid: int
    st_size: int
    st_mtime: int
    st_rdev: int


class DiffOutput(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def delete_marker(self, path: str) -> None:
        pass

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


class DiffOutputDryRun(DiffOutput):
    def delete_marker(self, path: str) -> None:
        LOGGER.info("Delete marker %s", path)

    def write_dir(self, path: str, st: StatInfo) -> None:
        LOGGER.info("Write dir %s", path)
        assert st

    def write_file(self, path: str, st: StatInfo, reader) -> None:
        LOGGER.info("Write file %s", path)
        assert st
        assert reader

    def write_symlink(self, path: str, st: StatInfo, linkname: str) -> None:
        LOGGER.info("Symlink %s -> %s", path, linkname)
        assert st

    def write_other(self, path: str, st: StatInfo) -> None:
        LOGGER.info("Other file %s", path)
        assert st
