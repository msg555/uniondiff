import tempfile

import pytest

from dirdiff.output_file import OutputBackendFile


@pytest.fixture
def file_backend():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield OutputBackendFile(tmp_dir)


@pytest.fixture
def file_backend_preserve():
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield OutputBackendFile(tmp_dir, preserve_owners=True)
