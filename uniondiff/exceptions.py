class UnionDiffException(Exception):
    """
    Generic base exception for any expected failure in uniondiff. If the exception
    raises to the top level the CLI will simply print the exception message and
    exit with the passed exit_code.
    """

    def __init__(self, msg: str, *, exit_code: int = 1) -> None:
        super().__init__(msg)
        self.exit_code = exit_code


class UnionDiffIOException(UnionDiffException):
    """Any exception relating to an I/O failure"""


class UnionDiffInputException(UnionDiffIOException):
    """An input error exception"""


class UnionDiffOutputException(UnionDiffIOException):
    """An output error exception"""
