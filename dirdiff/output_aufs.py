import io
import logging
import stat

from dirdiff.osshim import posix_basename, posix_join, posix_split
from dirdiff.output import DiffOutputForwarding, OutputBackend, StatInfo

LOGGER = logging.getLogger(__name__)


class DiffOutputAufs(DiffOutputForwarding):
    WHITEOUT_PREFIX = ".wh."

    def __init__(self, backend: OutputBackend) -> None:
        super().__init__(backend)
        self.whiteout_uid = 0
        self.whiteout_gid = 0

    @classmethod
    def is_whiteout_path(cls, path: str) -> bool:
        return posix_basename(path).startswith(cls.WHITEOUT_PREFIX)

    def delete_marker(self, path: str) -> None:
        head, tail = posix_split(path)
        self.backend.write_file(
            posix_join(head, self.WHITEOUT_PREFIX + tail),
            StatInfo(
                mode=stat.S_IFREG | 0o444,
                uid=self.whiteout_uid,
                gid=self.whiteout_gid,
                size=0,
                mtime=0,
                rdev=0,
            ),
            io.BytesIO(b""),
        )

    def write_file(self, path: str, st: StatInfo, reader) -> None:
        if self.is_whiteout_path(path):
            LOGGER.warning("Refusing to write spurious whiteout path %s", path)
            return
        super().write_file(path, st, reader)
