import logging
import os
import socket
import stat

from uniondiff.exceptions import UnionDiffOutputException
from uniondiff.output import OutputBackend, StatInfo

LOGGER = logging.getLogger(__name__)


class OutputBackendFile(OutputBackend):
    """
    Backend implementation for writing diff output directly to the file system.
    """

    SUPPORTS_PRESERVE_OWNERS = hasattr(os, "lchown") and hasattr(os, "fchown")

    def __init__(self, base_path: str, *, preserve_owners=False) -> None:
        self.base_path = base_path
        self.preserve_owners = preserve_owners
        if preserve_owners and not self.SUPPORTS_PRESERVE_OWNERS:
            raise ValueError("OS does not support preserving owners")

    def _full_path(self, path: str) -> str:
        return os.path.normpath(os.path.join(self.base_path, path))

    def _fixup_owners(self, full_path: str, st: StatInfo, *, fd: int = -1) -> None:
        if not self.preserve_owners:
            return
        try:
            if fd == -1:
                os.lchown(full_path, st.uid, st.gid)
            else:
                os.fchown(fd, st.uid, st.gid)
        except OSError as exc:
            raise UnionDiffOutputException(f"failed to chown object: {exc}") from exc

    def write_dir(self, path: str, st: StatInfo) -> None:
        full_path = self._full_path(path)
        os.mkdir(
            full_path,
            mode=stat.S_IMODE(st.mode),
        )
        self._fixup_owners(full_path, st)

    def write_file(self, path: str, st: StatInfo, reader) -> None:
        full_path = self._full_path(path)
        fd = os.open(full_path, os.O_WRONLY | os.O_CREAT, mode=stat.S_IMODE(st.mode))
        with os.fdopen(fd, "wb") as fout:
            while data := reader.read(2**16):
                fout.write(data)
            self._fixup_owners(full_path, st, fd=fd)

    def write_symlink(self, path: str, st: StatInfo, linkname: str) -> None:
        full_path = self._full_path(path)
        os.symlink(linkname, full_path)
        self._fixup_owners(full_path, st)

    def write_other(self, path: str, st: StatInfo) -> None:
        full_path = self._full_path(path)
        if stat.S_IFMT(st.mode) in (
            stat.S_IFCHR,
            stat.S_IFBLK,
            stat.S_IFIFO,
        ) and hasattr(os, "mknod"):
            os.mknod(full_path, mode=st.mode, device=st.rdev)
        elif stat.S_ISSOCK(st.mode) and hasattr(socket, "AF_UNIX"):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.bind(full_path)
            sock.close()
            os.chmod(full_path, stat.S_IMODE(st.mode))
        else:
            raise UnionDiffOutputException("Unsupported file type")

        self._fixup_owners(full_path, st)
