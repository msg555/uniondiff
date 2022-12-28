import logging
import sys
import tarfile

from dirdiff.differ import Differ
from dirdiff.output_overlay import DiffOutputOverlayTar


def main():
    # Just placeholder entrypoint for now
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
    )

    with tarfile.open(mode="w|", fileobj=sys.stdout.buffer) as tf:
        output = DiffOutputOverlayTar(tf)
        differ = Differ(sys.argv[1], sys.argv[2], output)
        differ.diff()


if __name__ == "__main__":
    main()
