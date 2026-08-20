import logging
from typing import cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


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


def register_exception_handlers(app: FastAPI) -> None:
    async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
        err = cast(DomainError, exc)
        logger.warning(
            "Domain error serving %s %s with status %s",
            request.method,
            request.url.path,
            err.status_code,
        )
        return JSONResponse(status_code=err.status_code, content={"detail": err.detail})

    async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
        err = cast(RequestValidationError, exc)
        detail = [
            {"type": error["type"], "loc": list(error["loc"]), "msg": error["msg"]}
            for error in err.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content={"detail": detail},
        )

    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled error serving %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "Internal server error"},
        )

    app.add_exception_handler(DomainError, handle_domain_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
