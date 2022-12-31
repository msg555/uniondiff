import logging

from dirdiff.output import OutputBackend, StatInfo

LOGGER = logging.getLogger(__name__)


class OutputBackendFile(OutputBackend):
    def __init__(self, path: str, *, ignore_owners=True) -> None:
        self.path = path
        self.ignore_owners = ignore_owners

    def write_dir(self, path: str, st: StatInfo) -> None:
        pass

    def write_file(self, path: str, st: StatInfo, reader) -> None:
        pass

    def write_symlink(self, path: str, st: StatInfo, linkname: str) -> None:
        pass

    def write_other(self, path: str, st: StatInfo) -> None:
        pass
