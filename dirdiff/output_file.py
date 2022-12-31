import logging
import os
import socket
import stat

from dirdiff.output import OutputBackend, StatInfo

LOGGER = logging.getLogger(__name__)


class OutputBackendFile(OutputBackend):
    def __init__(self, base_path: str, *, ignore_owners=True) -> None:
        self.base_path = base_path
        self.ignore_owners = ignore_owners

    def _full_path(self, path: str) -> str:
        return os.path.normpath(os.path.join(self.base_path, path))

    def _fixup_owners(self, path: str, st: StatInfo, *, fd: int = -1) -> None:
        if self.ignore_owners:
            return
        if fd == -1:
            os.lchown(path, st.st_uid, st.st_gid)
        else:
            os.fchown(fd, st.st_uid, st.st_gid)

    def write_dir(self, path: str, st: StatInfo) -> None:
        full_path = self._full_path(path)
        os.mkdir(
            full_path,
            mode=stat.S_IMODE(st.st_mode),
        )
        self._fixup_owners(path, st)

    def write_file(self, path: str, st: StatInfo, reader) -> None:
        full_path = self._full_path(path)
        fd = os.open(full_path, os.O_WRONLY | os.O_CREAT, mode=stat.S_IMODE(st.st_mode))
        with os.fdopen(fd, "wb") as fout:
            while data := reader.read():
                fout.write(data)
            self._fixup_owners(path, st, fd=fd)

    def write_symlink(self, path: str, st: StatInfo, linkname: str) -> None:
        full_path = self._full_path(path)
        os.symlink(linkname, full_path)
        self._fixup_owners(path, st)

    def write_other(self, path: str, st: StatInfo) -> None:
        full_path = self._full_path(path)
        if stat.S_IFMT(st.st_mode) in (stat.S_IFCHR, stat.S_IFBLK, stat.S_IFIFO):
            try:
                os.mknod(full_path, mode=st.st_mode, device=st.st_rdev)
            except PermissionError as err:
                LOGGER.warning("Failed to create device file: %s", err)
                return
        elif stat.S_ISSOCK(st.st_mode):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            sock.bind(full_path)
            sock.close()
            os.chmod(full_path, stat.S_IMODE(st.st_mode))
        else:
            LOGGER.warning("Ignoring %s: unknown file type", path)

        self._fixup_owners(path, st)
