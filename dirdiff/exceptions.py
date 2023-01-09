class DirDiffException(Exception):
    def __init__(self, msg: str, *, exit_code: int = 1) -> None:
        super().__init__(msg)
        self.exit_code = exit_code


class DirDiffInputException(DirDiffException):
    pass