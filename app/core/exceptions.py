from collections.abc import Mapping

from app.core.error_codes import ErrorCode

ErrorParams = Mapping[str, str | int]


class DomainError(Exception):
    status_code = 500
    code: ErrorCode = ErrorCode.UNEXPECTED

    def __init__(
        self,
        detail: str,
        *,
        code: ErrorCode | None = None,
        params: ErrorParams | None = None,
    ) -> None:
        self.detail = detail
        self.code = code if code is not None else type(self).code
        self.params: dict[str, str | int] = dict(params or {})
        super().__init__(detail)


class NotFoundError(DomainError):
    status_code = 404
    code = ErrorCode.NOT_FOUND


class ConflictError(DomainError):
    status_code = 409
    code = ErrorCode.CONFLICT


class AuthError(DomainError):
    status_code = 401
    code = ErrorCode.UNAUTHORIZED


class ForbiddenError(DomainError):
    status_code = 403
    code = ErrorCode.FORBIDDEN


class PayloadTooLargeError(DomainError):
    status_code = 413
    code = ErrorCode.PAYLOAD_TOO_LARGE
