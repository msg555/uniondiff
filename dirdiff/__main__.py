import argparse
import logging
import os
import sys
import tarfile
from contextlib import ExitStack

from dirdiff.differ import Differ
from dirdiff.output import OutputBackend
from dirdiff.output_aufs import DiffOutputAufs
from dirdiff.output_file import OutputBackendFile
from dirdiff.output_overlay import DiffOutputOverlay
from dirdiff.output_tar import OutputBackendTarfile

LOGGER = logging.getLogger(__name__)

DIFF_CLASSES = {
    "overlay": DiffOutputOverlay,
    "aufs": DiffOutputAufs,
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Computes the directory difference `upper = merged - lower`"
    )
    parser.add_argument(
        "merged",
        help="Path to the target merged directory, the left operand of the subtraction",
    )
    parser.add_argument(
        "lower",
        help="Path to the starting lower directory, the right operand of the subtraction",
    )
    parser.add_argument(
        "--diff-type",
        default="overlay",
        choices=DIFF_CLASSES,
    )
    parser.add_argument(
        "--output-type",
        default="tar",
        choices=("file", "tar", "tgz"),
        help="Type of archive to produce",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="",
        help="Output path or directory. Defaults to stdout for tar archives",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
    )
    return parser.parse_args()


def setup_logging(verbose: int) -> None:
    log_level = logging.ERROR
    if verbose > 2:
        log_level = logging.DEBUG
    elif verbose > 1:
        log_level = logging.INFO
    elif verbose > 0:
        log_level = logging.WARNING

    logging.basicConfig(
        level=log_level,
        stream=sys.stderr,
    )


def main() -> int:
    os.umask(0)

    args = parse_args()
    setup_logging(args.verbose)

    with ExitStack() as stack:
        backend: OutputBackend
        if args.output_type in ("tar", "tgz"):
            if args.output:
                tf = stack.enter_context(tarfile.open(args.output, mode="w|"))
            else:
                tf = stack.enter_context(
                    tarfile.open(mode="w|", fileobj=sys.stdout.buffer)
                )
            backend = OutputBackendTarfile(tf)
        else:
            assert args.output_type == "file"

            if not args.output:
                LOGGER.error(
                    "--output file path must be provided with 'file' output type"
                )
                return 1

            if os.path.exists(args.output):
                LOGGER.error("output path already exists")
                return 1

            backend = OutputBackendFile(args.output)

        diff_output = DIFF_CLASSES[args.diff_type](backend)
        differ = Differ(args.merged, args.lower, diff_output)
        differ.diff()

    return 0


if __name__ == "__main__":
    sys.exit(main())
