"""Application errors. These classes do not read the request."""


class AppError(Exception):
    """Error that keeps an HTTP status and a stable code."""

    def __init__(self, message: str, status: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


class NotFoundError(AppError):
    """Missing page or record. The API code is not_found."""

    def __init__(self, message: str = 'The page could not be loaded.') -> None:
        super().__init__(message, 404, 'not_found')


class ForbiddenError(AppError):
    """Blocked request. The API code is forbidden."""

    def __init__(self, message: str = 'The page could not be loaded.') -> None:
        super().__init__(message, 403, 'forbidden')


class UnavailableError(AppError):
    """Unexpected failure. The API code is unavailable."""

    def __init__(self, message: str = 'The page could not be loaded.') -> None:
        super().__init__(message, 500, 'unavailable')
