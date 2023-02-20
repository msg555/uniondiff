import argparse
import logging
import os
import sys
import tarfile
from contextlib import ExitStack
from typing import Union

from uniondiff.differ import Differ, DifferOptions
from uniondiff.exceptions import UnionDiffException
from uniondiff.output import DiffOutput, DiffOutputDryRun, OutputBackend
from uniondiff.output_aufs import DiffOutputAufs
from uniondiff.output_file import OutputBackendFile
from uniondiff.output_overlay import DiffOutputOverlay
from uniondiff.output_tar import OutputBackendTarfile

LOGGER = logging.getLogger(__name__)

DIFF_CLASSES = {
    "overlay": DiffOutputOverlay,
    "aufs": DiffOutputAufs,
}


def parse_args(args=None) -> argparse.Namespace:
    """
    Parse command line or passed arguments return the parsed namespace object
    as given from the argparse module.
    """
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
        help="Selects the kind of diff to perform. "
        "Mostly this affects how deletions are represented.",
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
        choices=("file", "tar"),
        help="Type of archive to interpret merged path as",
    )
    parser.add_argument(
        "--lower-input-type",
        default=None,
        choices=("file", "tar"),
        help="Type of archive to interpret lower path as",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="",
        help="Output path or directory. Defaults to stdout for tar archives",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="count",
        default=0,
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_const",
        default=False,
        const=True,
        help="Allow write to TTY or existing path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_const",
        default=False,
        const=True,
        help="Just print out what files would be written or deleted in the diff",
    )
    parser.add_argument(
        "--input-best-effort",
        action="store_const",
        default=False,
        const=True,
        help="Ignore input errors from merged and lower operands as much as possible",
    )
    parser.add_argument(
        "--output-best-effort",
        action="store_const",
        default=False,
        const=True,
        help="Ignore output errors as much as possible",
    )
    if OutputBackendFile.SUPPORTS_PRESERVE_OWNERS:
        parser.add_argument(
            "-p",
            "--preserve-owners",
            action="store_const",
            default=False,
            const=True,
            help="Attempt to chown files to preserve ownership, only applies to file-based output",
        )
    return parser.parse_args(args=args)


def setup_logging(verbose: int) -> None:
    """Set our logging level and format based on verbosity level"""
    log_level = logging.ERROR
    log_format = "%(message)s"
    if verbose > 2:
        log_level = logging.DEBUG
        log_format = "%(levelname)s(%(module)s): %(message)s"
    elif verbose > 1:
        log_level = logging.INFO
        log_format = "%(levelname)s: %(message)s"
    elif verbose > 0:
        log_level = logging.WARNING

    logging.basicConfig(
        format=log_format,
        level=log_level,
        stream=sys.stderr,
    )


def _get_input_dir(
    stack: ExitStack, path: str, input_type: str
) -> Union[str, tarfile.TarFile]:
    if not input_type and os.path.isdir(path):
        input_type = "file"
    if input_type == "file":
        return path

    try:
        return stack.enter_context(tarfile.open(path, mode="r"))
    except FileNotFoundError as exc:
        raise UnionDiffException(f"Input path {repr(path)} does not exist") from exc
    except (OSError, tarfile.TarError) as exc:
        raise UnionDiffException(
            f"Failed to open input file {repr(path)}: {exc}"
        ) from exc


def _get_backend(
    stack: ExitStack, output_type: str, output: str, force: bool, preserve_owners: bool
) -> OutputBackend:
    # pylint: disable=consider-using-with
    if output_type in ("tar", "tgz"):
        tar_mode = "w|gz" if output_type == "tgz" else "w|"
        if output:
            tf = stack.enter_context(tarfile.open(output, mode=tar_mode))
        else:
            if not force and sys.stdout.isatty():
                raise UnionDiffException("Refusing to write tar file to terminal")
            tf = stack.enter_context(
                tarfile.open(mode=tar_mode, fileobj=sys.stdout.buffer)
            )
        if preserve_owners:
            LOGGER.warning("Ignoring flag --preserve-owners for archive output")
        return OutputBackendTarfile(tf)

    assert output_type == "file"

    if not output:
        raise UnionDiffException(
            "--output file path must be provided with 'file' output type"
        )

    if not force and os.path.exists(output):
        raise UnionDiffException("output path already exists")

    os.umask(0)
    return OutputBackendFile(output, preserve_owners=preserve_owners)


def main(args=None) -> int:
    """Main CLI entrypoint, optionally using passed arguments rather than sys.argv"""
    args = parse_args(args=args)
    setup_logging(1 + args.verbose - args.quiet)

    with ExitStack() as stack:
        merged = _get_input_dir(stack, args.merged, args.merged_input_type)
        lower = _get_input_dir(stack, args.lower, args.lower_input_type)

        diff_output: DiffOutput
        if args.dry_run:
            diff_output = DiffOutputDryRun()
        else:
            diff_output = DIFF_CLASSES[args.diff_type](
                _get_backend(
                    stack,
                    args.output_type,
                    args.output,
                    args.force,
                    getattr(args, "preserve_owners", False),
                )
            )

        options = DifferOptions(
            input_error_strict=not args.input_best_effort,
            output_error_strict=not args.output_best_effort,
        )

        differ = Differ(merged, lower, diff_output, options=options)
        differ.diff()

    return 0
