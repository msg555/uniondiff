import logging
import sys

from dirdiff.cli import main
from dirdiff.exceptions import (
    DirDiffException,
    DirDiffInputException,
    DirDiffOutputException,
)

LOGGER = logging.getLogger(__name__)

try:
    sys.exit(main())
except DirDiffException as exc:
    LOGGER.error("%s", exc)
    if isinstance(exc, DirDiffInputException):
        LOGGER.warning("use --input-best-effort to ignore this error")
    elif isinstance(exc, DirDiffOutputException):
        LOGGER.warning("use --output-best-effort to ignore this error")
    sys.exit(exc.exit_code)
