import logging
import os
import stat
import tarfile
from tarfile import TarFile, TarInfo

from dirdiff.output import OutputBackend, StatInfo

LOGGER = logging.getLogger(__name__)


class OutputBackendTarfile(OutputBackend):
    def __init__(self, tf: TarFile, *, archive_root=".") -> None:
        self.tf = tf
        self.archive_root = archive_root

    def _get_tar_info(self, name: str, st: StatInfo) -> TarInfo:
        ti = TarInfo(os.path.join(self.archive_root, name))
        ti.mode = stat.S_IMODE(st.st_mode)
        ti.mtime = st.st_mtime
        ti.uid = st.st_uid
        ti.gid = st.st_gid
        if stat.S_ISBLK(st.st_mode) or stat.S_ISCHR(st.st_mode):
            ti.devmajor = os.major(st.st_rdev)
            ti.devminor = os.minor(st.st_rdev)

        return ti

    def write_dir(self, path: str, st: StatInfo) -> None:
        ti = self._get_tar_info(path, st)
        ti.type = tarfile.DIRTYPE
        self.tf.addfile(ti)

    def write_file(self, path: str, st: StatInfo, reader) -> None:
        ti = self._get_tar_info(path, st)
        ti.type = tarfile.REGTYPE
        ti.size = st.st_size
        self.tf.addfile(ti, reader)

    def write_symlink(self, path: str, st: StatInfo, linkname: str) -> None:
        ti = self._get_tar_info(path, st)
        ti.type = tarfile.SYMTYPE
        ti.linkname = linkname
        self.tf.addfile(ti)

    def write_other(self, path: str, st: StatInfo) -> None:
        ti = self._get_tar_info(path, st)
        if stat.S_ISSOCK(st.st_mode):
            # Sockets are not supported in tar format
            LOGGER.warning("Converting socket %s to fifo", path)
            ti.type = tarfile.FIFOTYPE
        elif stat.S_ISBLK(st.st_mode):
            ti.type = tarfile.BLKTYPE
        elif stat.S_ISCHR(st.st_mode):
            ti.type = tarfile.CHRTYPE
        elif stat.S_ISFIFO(st.st_mode):
            ti.type = tarfile.FIFOTYPE
        else:
            LOGGER.warning("Ignoring %s: unknown file type", path)
            return

        self.tf.addfile(ti)
