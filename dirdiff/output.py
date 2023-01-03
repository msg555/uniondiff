import abc
import logging

from dirdiff.filelib import StatInfo

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
