import hashlib
import os
import tarfile
import tempfile

from uniondiff.cli import main


def tar_summarize(tf: tarfile.TarFile):
    """
    Construct a datastructure summarizing a tar archive's structure for use with
    diffing to test for changes.
    """
    result = {}
    while ti := tf.next():
        assert ti.name == "." or ti.name.startswith("./")
        assert ti.name not in result
        parent = os.path.dirname(ti.name)

        if parent:
            assert parent in result

        content_hash = ""
        if ti.isfile():
            hsh = hashlib.sha256()
            f = tf.extractfile(ti)
            assert f is not None
            with f:
                while data := f.read(2**16):
                    hsh.update(data)
            content_hash = hsh.hexdigest()

        result[ti.name] = {
            "uid": ti.uid,
            "gid": ti.gid,
            "mode": ti.mode,
            "size": ti.size,
            "mtime": ti.mtime,
            "typ": ti.type,
            "content_hash": content_hash,
        }
    return result


def run_test(name: str, diff_type="overlay", expected_name="diff.tgz") -> None:
    """
    For a given test case compute the directory difference of merged
    and lower and compare it to the expected output.
    """
    test_path = os.path.join(os.path.dirname(__file__), "cases", name)
    with tempfile.NamedTemporaryFile(delete=False) as tmpf:
        tmp_name = tmpf.name

    try:
        args = [
            os.path.join(test_path, "merged.tgz"),
            os.path.join(test_path, "lower.tgz"),
            "--output",
            tmp_name,
            "--diff-type",
            diff_type,
        ]
        result = main(args=args)
        assert result == 0

        with tarfile.open(tmp_name, mode="r|") as tf:
            summary = tar_summarize(tf)
    finally:
        os.remove(tmp_name)

    with tarfile.open(os.path.join(test_path, expected_name), mode="r|gz") as tf:
        expected_summary = tar_summarize(tf)

    assert summary == expected_summary


def test_generic():
    """Test several different misc things"""
    run_test("generic")


def test_generic_aufs():
    """Test several different misc things"""
    run_test("generic", diff_type="aufs", expected_name="diff-aufs.tgz")


def test_backslash():
    """Test that files with backslashes work okay for tar archives."""
    run_test("generic")
