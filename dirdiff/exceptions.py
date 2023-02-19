class DirDiffException(Exception):
    """
    Generic base exception for any expected failure in dirdiff. If the exception
    raises to the top level the CLI will simply print the exception message and
    exit with the passed exit_code.
    """

    def __init__(self, msg: str, *, exit_code: int = 1) -> None:
        super().__init__(msg)
        self.exit_code = exit_code


class DirDiffIOException(DirDiffException):
    """Any exception relating to an I/O failure"""


class DirDiffInputException(DirDiffIOException):
    """An input error exception"""


class DirDiffOutputException(DirDiffIOException):
    """An output error exception"""
