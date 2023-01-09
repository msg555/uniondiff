import sys

from dirdiff.cli import main
from dirdiff.exceptions import DirDiffException, DirDiffInputException

try:
    sys.exit(main())
except DirDiffException as exc:
    print(exc)
    if isinstance(exc, DirDiffInputException):
        print("use --input-best-effort to ignore this error")
    sys.exit(exc.exit_code)
