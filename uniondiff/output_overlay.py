import logging
import stat

from uniondiff.exceptions import UnionDiffOutputException
from uniondiff.output import DiffOutputForwarding, OutputBackend, StatInfo

LOGGER = logging.getLogger(__name__)


class DiffOutputOverlay(DiffOutputForwarding):
    """
    Output forwarder that converts deletion markers into overlay-style
    deletion markers using the char device (0, 0).
    """

    def __init__(self, backend: OutputBackend) -> None:
        super().__init__(backend)
        self.whiteout_uid = 0
        self.whiteout_gid = 0

    def delete_marker(self, path: str) -> None:
        """Write a char device with major/minor 0/0 to indicate a deleted file"""
        self.backend.write_other(
            path,
            StatInfo(
                mode=stat.S_IFCHR | 0o444,
                uid=self.whiteout_uid,
                gid=self.whiteout_gid,
                size=0,
                mtime=0,
                rdev=0,
            ),
        )

    def write_other(self, path: str, st: StatInfo) -> None:
        """
        Forward most writes but raise an exception if we try to write a
        character device that would be interpretted as a deletion.
        """
        if stat.S_ISCHR(st.mode) and st.rdev == 0:
            raise UnionDiffOutputException(
                f"Refusing to write spurious whiteout character device at {path!r}"
            )
        super().write_other(path, st)
