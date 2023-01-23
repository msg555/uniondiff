import logging
import os
import stat
import tarfile
from tarfile import TarFile, TarInfo

from dirdiff.exceptions import DirDiffOutputException
from dirdiff.osshim import major, minor
from dirdiff.output import OutputBackend, StatInfo

LOGGER = logging.getLogger(__name__)


class OutputBackendTarfile(OutputBackend):
    def __init__(self, tf: TarFile, *, archive_root=".") -> None:
        self.tf = tf
        self.archive_root = archive_root

    def _get_tar_info(self, name: str, st: StatInfo) -> TarInfo:
        if name in (".", os.path.sep):
            arch_name = self.archive_root
        elif name.startswith(f".{os.path.sep}"):
            arch_name = os.path.join(self.archive_root, name[2:])
        elif name.startswith(os.path.sep):
            arch_name = os.path.join(self.archive_root, name[1:])
        else:
            arch_name = os.path.join(self.archive_root, name)
        ti = TarInfo(arch_name)
        ti.mode = stat.S_IMODE(st.mode)
        ti.mtime = st.mtime
        ti.uid = st.uid
        ti.gid = st.gid
        if stat.S_ISBLK(st.mode) or stat.S_ISCHR(st.mode):
            ti.devmajor = major(st.rdev)
            ti.devminor = minor(st.rdev)

        return ti

    def write_dir(self, path: str, st: StatInfo) -> None:
        ti = self._get_tar_info(path, st)
        ti.type = tarfile.DIRTYPE
        self.tf.addfile(ti)

    def write_file(self, path: str, st: StatInfo, reader) -> None:
        ti = self._get_tar_info(path, st)
        ti.type = tarfile.REGTYPE
        ti.size = st.size
        self.tf.addfile(ti, reader)

    def write_symlink(self, path: str, st: StatInfo, linkname: str) -> None:
        ti = self._get_tar_info(path, st)
        ti.type = tarfile.SYMTYPE
        ti.linkname = linkname
        self.tf.addfile(ti)

    def write_other(self, path: str, st: StatInfo) -> None:
        ti = self._get_tar_info(path, st)
        if stat.S_ISBLK(st.mode):
            ti.type = tarfile.BLKTYPE
        elif stat.S_ISCHR(st.mode):
            ti.type = tarfile.CHRTYPE
        elif stat.S_ISFIFO(st.mode):
            ti.type = tarfile.FIFOTYPE
        else:
            raise DirDiffOutputException("file type not supported by tar archives")

        self.tf.addfile(ti)
