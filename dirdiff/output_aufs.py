import io
import logging
import os
import stat

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
        return os.path.basename(path).startswith(cls.WHITEOUT_PREFIX)

    def delete_marker(self, path: str) -> None:
        head, tail = os.path.split(path)
        self.backend.write_file(
            os.path.join(head, self.WHITEOUT_PREFIX + tail),
            StatInfo(
                st_mode=stat.S_IFREG | 0o444,
                st_uid=self.whiteout_uid,
                st_gid=self.whiteout_gid,
                st_size=0,
                st_mtime=0,
                st_rdev=0,
            ),
            io.BytesIO(b""),
        )

    def write_file(self, path: str, st: StatInfo, reader) -> None:
        if self.is_whiteout_path(path):
            LOGGER.warning("Refusing to write spurious whiteout path %s", path)
            return
        super().write_file(path, st, reader)
