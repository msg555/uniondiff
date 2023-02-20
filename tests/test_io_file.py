import io
import os
import stat

import pytest

from uniondiff.filelib import DirectoryManager, StatInfo
from uniondiff.osshim import major, makedev, minor

# pylint: disable=redefined-outer-name


def _check_mode(actual: int, expected: int) -> None:
    """
    Check that the file type and permissions match. On windows we ignore the
    permissions since they aren't supported. Note that some file systems, even on
    unix systems, don't support permissions (like NTFS). For the purposes of this test
    however we assume that an appropriate unix-capable file system is used for temp
    directories on a unix system.
    """
    assert stat.S_IFMT(actual) == stat.S_IFMT(expected)
    if os.name == "nt":
        return
    actual_perms = stat.S_IMODE(actual)
    expected_perms = stat.S_IMODE(expected)
    assert actual_perms == expected_perms


def stat_with_defaults(
    mode: int = 0o755,
    uid: int = 1234,
    gid: int = 4567,
    size: int = 0,
    mtime: int = 0,
    rdev: int = 0,
) -> StatInfo:
    """Helper to generate a stat entry with defaults"""
    return StatInfo(mode, uid, gid, size, mtime, rdev)


def test_file_write_dir(file_backend):
    """Test writing a directory than reading the directory"""
    mode = 0o755 | stat.S_IFDIR
    file_name = "my-dir"
    st = stat_with_defaults(mode=mode)
    file_backend.write_dir(file_name, st)

    file_path = os.path.join(file_backend.base_path, file_name)
    st = os.lstat(file_path)
    _check_mode(st.st_mode, mode)
    assert not os.listdir(file_path)

    with DirectoryManager(file_backend.base_path) as dm:
        assert [(entry.name, entry.is_dir()) for entry in dm] == [(file_name, True)]
        with dm.child_dir(file_name) as sdm:
            _check_mode(sdm.stat.mode, mode)
            assert [entry.name for entry in sdm] == []


def test_file_write_reg(file_backend):
    """Test writing a regular file than reading the regular file"""
    mode = 0o644 | stat.S_IFREG
    data = b"Hello uniondiff!"
    file_name = "my-file"

    st = stat_with_defaults(mode=mode, size=len(data))
    file_backend.write_file(file_name, st, io.BytesIO(data))

    file_path = os.path.join(file_backend.base_path, file_name)
    st = os.lstat(file_path)
    _check_mode(st.st_mode, mode)
    with open(file_path, "rb") as fdata:
        assert fdata.read() == data

    with DirectoryManager(file_backend.base_path) as dm:
        assert [(entry.name, entry.is_file()) for entry in dm] == [(file_name, True)]
        with dm.child_file(file_name) as fm:
            _check_mode(fm.stat.mode, mode)
            with fm.reader() as reader:
                assert reader.read(2**16) == data


def test_file_write_link(file_backend):
    """Test writing a file and a symlink pointing to it then reading the same"""
    mode = 0o644 | stat.S_IFREG
    data = b"Hello uniondiff!"
    file_name = "my-file"

    st = stat_with_defaults(mode=mode, size=len(data))
    file_backend.write_file(file_name, st, io.BytesIO(data))

    sym_mode = 0o777 | stat.S_IFLNK
    sym_file_name = "my-link"
    sym_st = stat_with_defaults(mode=sym_mode)
    file_backend.write_symlink(sym_file_name, sym_st, file_name)

    sym_file_path = os.path.join(file_backend.base_path, sym_file_name)
    st = os.lstat(sym_file_path)
    # Permission bits on symlinks are irrelevant, some OS/FS do different things
    assert stat.S_ISLNK(st.st_mode)
    assert os.readlink(sym_file_path) == file_name

    st = os.stat(sym_file_path)
    _check_mode(st.st_mode, mode)
    with open(sym_file_path, "rb") as fdata:
        assert fdata.read() == data

    with DirectoryManager(file_backend.base_path) as dm:
        assert sorted(
            (entry.name, entry.is_file(follow_symlinks=False)) for entry in dm
        ) == sorted(((file_name, True), (sym_file_name, False)))
        with dm.child_path(sym_file_name) as pm:
            assert stat.S_ISLNK(pm.stat.mode)
            assert pm.linkname == file_name


@pytest.mark.unix
@pytest.mark.cap
@pytest.mark.cap_mknod
@pytest.mark.parametrize(
    "ftype",
    [
        pytest.param(stat.S_IFCHR, id="chr"),
        pytest.param(stat.S_IFBLK, id="blk"),
    ],
)
def test_file_write_device(ftype, file_backend):
    """Test writing a character/block device and accessing"""
    mode = 0o600 | ftype
    file_name = "my-dev"
    dev_major = 12
    dev_minor = 7

    st = stat_with_defaults(mode=mode, rdev=makedev(dev_major, dev_minor))
    file_backend.write_other(file_name, st)

    file_path = os.path.join(file_backend.base_path, file_name)
    st = os.lstat(file_path)
    _check_mode(st.st_mode, mode)
    assert major(st.st_rdev) == dev_major
    assert minor(st.st_rdev) == dev_minor

    with DirectoryManager(file_backend.base_path) as dm:
        assert [(entry.name, entry.is_file()) for entry in dm] == [(file_name, False)]
        with dm.child_path(file_name) as pm:
            _check_mode(pm.stat.mode, mode)
            assert stat.S_IFMT(pm.stat.mode) == ftype
            assert major(pm.stat.rdev) == dev_major
            assert minor(pm.stat.rdev) == dev_minor


@pytest.mark.unix
@pytest.mark.cap
@pytest.mark.cap_chown
def test_file_write_chown(file_backend_preserve):
    """Test ownership preservation with a regular file"""
    mode = 0o644 | stat.S_IFREG
    data = b"Hello uniondiff!"
    file_name = "my-file"
    uid = 123
    gid = 543

    st = stat_with_defaults(mode=mode, size=len(data), uid=uid, gid=gid)
    file_backend_preserve.write_file(file_name, st, io.BytesIO(data))

    file_path = os.path.join(file_backend_preserve.base_path, file_name)
    st = os.lstat(file_path)
    _check_mode(st.st_mode, mode)
    assert st.st_uid == uid
    assert st.st_gid == gid
    with open(file_path, "rb") as fdata:
        assert fdata.read() == data

    with DirectoryManager(file_backend_preserve.base_path) as dm:
        assert [(entry.name, entry.is_file()) for entry in dm] == [(file_name, True)]
        with dm.child_file(file_name) as fm:
            assert fm.stat.uid == uid
            assert fm.stat.gid == gid
            _check_mode(fm.stat.mode, mode)
            with fm.reader() as reader:
                assert reader.read(2**16) == data


@pytest.mark.unix
@pytest.mark.parametrize(
    "ftype",
    [
        pytest.param(stat.S_IFSOCK, id="sock"),
        pytest.param(stat.S_IFIFO, id="fifo"),
    ],
)
def test_file_write_sock(ftype, file_backend):
    """Test writing a socket and accessing the socket"""
    mode = 0o600 | ftype
    file_name = "my-sock"

    st = stat_with_defaults(mode=mode)
    file_backend.write_other(file_name, st)

    file_path = os.path.join(file_backend.base_path, file_name)
    st = os.lstat(file_path)
    _check_mode(st.st_mode, mode)

    with DirectoryManager(file_backend.base_path) as dm:
        assert [(entry.name, entry.is_file()) for entry in dm] == [(file_name, False)]
        with dm.child_path(file_name) as pm:
            _check_mode(pm.stat.mode, mode)
            assert stat.S_IFMT(pm.stat.mode) == ftype
