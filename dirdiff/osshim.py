# pylint: disable=redefined-outer-name,unused-import

try:
    from os import makedev
except ImportError:

    def makedev(major: int, minor: int, /) -> int:
        return major << 8 | minor


try:
    from os import major
except ImportError:

    def major(dev: int, /) -> int:
        return dev >> 8


try:
    from os import minor
except ImportError:

    def minor(dev: int, /) -> int:
        return dev & 0xFF
