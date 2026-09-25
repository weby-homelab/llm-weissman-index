"""Typed errors used by the LWI reference implementation."""


class LWIError(Exception):
    """Base class for expected LWI failures."""


class InputError(LWIError, ValueError):
    """Raised when a data object cannot satisfy the input contract."""

    def __init__(self, message: str, *, code: str = "INVALID_INPUT", path: str = "$") -> None:
        super().__init__(message)
        self.code = code
        self.path = path


class IneligibleError(LWIError):
    """Raised only for internal control flow when a result is not scoreable."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
