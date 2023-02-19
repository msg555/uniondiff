# pylint: disable=redefined-outer-name,unused-import
import os
from typing import List, Tuple

try:
    from posixpath import basename as posix_basename
    from posixpath import join as posix_join
    from posixpath import normpath as posix_norm
    from posixpath import split as posix_split
except ImportError:
    from os.path import basename as posix_basename
    from os.path import join as posix_join
    from os.path import normpath as posix_norm
    from os.path import split as posix_split

try:
    from os import makedev
except ImportError:

    def makedev(major: int, minor: int, /) -> int:
        """Replacement implementation for makedev when not available"""
        return major << 8 | minor


try:
    from os import major
except ImportError:

    def major(dev: int, /) -> int:
        """Replacement implementation for major when not available"""
        return dev >> 8


try:
    from os import minor
except ImportError:

    def minor(dev: int, /) -> int:
        """Replacement implementation for minor when not available"""
        return dev & 0xFF
