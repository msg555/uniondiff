import argparse
import logging
import os
import sys
import tarfile
from contextlib import ExitStack
from typing import Union

from dirdiff.differ import Differ
from dirdiff.output import OutputBackend
from dirdiff.output_aufs import DiffOutputAufs
from dirdiff.output_file import OutputBackendFile
from dirdiff.output_overlay import DiffOutputOverlay
from dirdiff.output_tar import OutputBackendTarfile

LOGGER = logging.getLogger(__name__)
GZIP_MAGIC_HEADER = "\x1f\x8b"

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
        "--merged-input-type",
        default=None,
        choices=("file", "tar", "tgz"),
        help="Type of archive to interpret merged path as",
    )
    parser.add_argument(
        "--lower-input-type",
        default=None,
        choices=("file", "tar", "tgz"),
        help="Type of archive to interpret lower path as",
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
    parser.add_argument(
        "--strict",
        action="store_const",
        default=False,
        const=True,
        help="Fail if there are any issues generating output",
    )
    parser.add_argument(
        "--skip-errors",
        action="store_const",
        default=False,
        const=True,
        help="Ignore most output errors and just do as much as possible",
    )
    return parser.parse_args()


def setup_logging(verbose: int) -> None:
    log_level = logging.ERROR
    log_format = "%(message)s"
    if verbose > 2:
        log_level = logging.DEBUG
        log_format = "%(levelname)s(%(module)s): %(message)s"
    elif verbose > 1:
        log_level = logging.INFO
        log_format = "%(levelname)s(%(module)s): %(message)s"
    elif verbose > 0:
        log_level = logging.WARNING
        log_format = "%(levelname)s: %(message)s"

    logging.basicConfig(
        format=log_format,
        level=log_level,
        stream=sys.stderr,
    )


def _get_input_dir(
    stack: ExitStack, path: str, input_type: str
) -> Union[str, tarfile.TarFile]:
    if not input_type:
        if os.path.isdir(path):
            input_type = "file"
        else:
            with open(path, "rb") as fdata:
                magic = fdata.read(len(GZIP_MAGIC_HEADER))
            input_type = "tgz" if magic == GZIP_MAGIC_HEADER else "tar"

    if input_type == "file":
        return path
    tar_mode = "r:gz" if input_type == "tgz" else "r"
    return stack.enter_context(tarfile.open(path, mode=tar_mode))


def main() -> int:
    args = parse_args()
    setup_logging(args.verbose)

    with ExitStack() as stack:
        backend: OutputBackend
        if args.output_type in ("tar", "tgz"):
            tar_mode = "w|gz" if args.output_type == "tgz" else "w|"
            if args.output:
                tf = stack.enter_context(tarfile.open(args.output, mode=tar_mode))
            else:
                if sys.stdout.isatty():
                    LOGGER.error("Refusing to write tar file to terminal")
                    return 1
                tf = stack.enter_context(
                    tarfile.open(mode=tar_mode, fileobj=sys.stdout.buffer)
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

            os.umask(0)
            backend = OutputBackendFile(args.output)

        merged = _get_input_dir(stack, args.merged, args.merged_input_type)
        lower = _get_input_dir(stack, args.lower, args.lower_input_type)
        diff_output = DIFF_CLASSES[args.diff_type](backend)
        differ = Differ(merged, lower, diff_output)
        differ.diff()

    return 0
