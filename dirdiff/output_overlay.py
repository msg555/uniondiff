import logging
import stat

from dirdiff.output import DiffOutputForwarding, OutputBackend, StatInfo

LOGGER = logging.getLogger(__name__)


class DiffOutputOverlay(DiffOutputForwarding):
    def __init__(self, backend: OutputBackend) -> None:
        super().__init__(backend)
        self.whiteout_uid = 0
        self.whiteout_gid = 0

    def delete_marker(self, path: str) -> None:
        self.backend.write_other(
            path,
            StatInfo(
                st_mode=stat.S_IFCHR | 0o444,
                st_uid=self.whiteout_uid,
                st_gid=self.whiteout_gid,
                st_size=0,
                st_mtime=0,
                st_rdev=0,
            ),
        )

    def write_other(self, path: str, st: StatInfo) -> None:
        if stat.S_ISCHR(st.st_mode) and st.st_rdev == 0:
            LOGGER.warning(
                "Refusing to write spurious whiteout character device at %s", path
            )
            return
        super().write_other(path, st)
