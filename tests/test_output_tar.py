import io
import os
import stat
import tarfile

import pytest

from dirdiff.filelib import StatInfo
from dirdiff.osshim import makedev
from dirdiff.output_tar import OutputBackendTarfile

DEFAULT_UID = 1234
DEFAULT_GID = 4567


def stat_with_defaults(
    mode: int = 0o755,
    uid: int = DEFAULT_UID,
    gid: int = DEFAULT_GID,
    size: int = 0,
    mtime: int = 0,
    rdev: int = 0,
) -> StatInfo:
    return StatInfo(mode, uid, gid, size, mtime, rdev)


def test_file_write_dir():
    mode = 0o755 | stat.S_IFDIR
    file_name = "my-dir"
    st = stat_with_defaults(mode=mode)

    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as tf:
        backend = OutputBackendTarfile(tf)
        backend.write_dir(file_name, st)

    data.seek(0)
    with tarfile.open(fileobj=data, mode="r") as tf:
        assert len(tf.getmembers()) == 1
        ti = tf.getmember(os.path.join(backend.archive_root, file_name))
        assert st.mode == mode
        assert ti.isdir()
        assert ti.uid == DEFAULT_UID
        assert ti.gid == DEFAULT_GID


def test_file_write_reg():
    mode = 0o644 | stat.S_IFREG
    file_data = b"Hello dirdiff!"
    file_name = "my-file"
    st = stat_with_defaults(mode=mode, size=len(file_data))

    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as tf:
        backend = OutputBackendTarfile(tf)
        backend.write_file(file_name, st, io.BytesIO(file_data))

    data.seek(0)
    with tarfile.open(fileobj=data, mode="r") as tf:
        assert len(tf.getmembers()) == 1
        ti = tf.getmember(os.path.join(backend.archive_root, file_name))
        assert st.mode == mode
        assert ti.isreg()
        assert ti.uid == DEFAULT_UID
        assert ti.gid == DEFAULT_GID
        with tf.extractfile(ti) as fdata:
            assert fdata.read() == file_data


def test_file_write_link():
    mode = 0o644 | stat.S_IFREG
    file_data = b"Hello dirdiff!"
    file_name = "my-file"
    st = stat_with_defaults(mode=mode, size=len(file_data))

    # Many file systems force these perms on symlink nodes.
    sym_mode = 0o777 | stat.S_IFLNK
    sym_file_name = "my-link"
    sym_st = stat_with_defaults(mode=sym_mode)

    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as tf:
        backend = OutputBackendTarfile(tf)
        backend.write_file(file_name, st, io.BytesIO(file_data))
        backend.write_symlink(sym_file_name, sym_st, file_name)

    data.seek(0)
    with tarfile.open(fileobj=data, mode="r") as tf:
        assert len(tf.getmembers()) == 2
        ti = tf.getmember(os.path.join(backend.archive_root, sym_file_name))
        assert ti.issym()
        assert ti.linkname == file_name
        assert ti.uid == DEFAULT_UID
        assert ti.gid == DEFAULT_GID


@pytest.mark.parametrize(
    "ftype,attest",
    [
        pytest.param(stat.S_IFCHR, lambda ti: ti.ischr(), id="chr"),
        pytest.param(stat.S_IFBLK, lambda ti: ti.isblk(), id="blk"),
    ],
)
def test_file_write_device(ftype, attest):
    mode = 0o600 | ftype
    file_name = "my-char"
    dev_major = 12
    dev_minor = 7
    st = stat_with_defaults(mode=mode, rdev=makedev(dev_major, dev_minor))

    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w") as tf:
        backend = OutputBackendTarfile(tf)
        backend.write_other(file_name, st)

    data.seek(0)
    with tarfile.open(fileobj=data, mode="r") as tf:
        assert len(tf.getmembers()) == 1
        ti = tf.getmember(os.path.join(backend.archive_root, file_name))
        assert attest(ti)
        assert ti.devmajor == dev_major
        assert ti.devminor == dev_minor
        assert ti.uid == DEFAULT_UID
        assert ti.gid == DEFAULT_GID
