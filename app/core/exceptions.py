class DomainError(Exception):
    status_code = 500

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(DomainError):
    status_code = 404


class ConflictError(DomainError):
    status_code = 409


class AuthError(DomainError):
    status_code = 401


class ForbiddenError(DomainError):
    status_code = 403


class PayloadTooLargeError(DomainError):
    status_code = 413
