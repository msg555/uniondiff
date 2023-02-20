import logging
import sys

from uniondiff.cli import main
from uniondiff.exceptions import (
    UnionDiffException,
    UnionDiffInputException,
    UnionDiffOutputException,
)

LOGGER = logging.getLogger(__name__)

try:
    sys.exit(main())
except UnionDiffException as exc:
    LOGGER.error("%s", exc)
    if isinstance(exc, UnionDiffInputException):
        LOGGER.warning("use --input-best-effort to ignore this error")
    elif isinstance(exc, UnionDiffOutputException):
        LOGGER.warning("use --output-best-effort to ignore this error")
    sys.exit(exc.exit_code)
