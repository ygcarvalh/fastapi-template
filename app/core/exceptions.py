from typing import cast

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


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


def register_exception_handlers(app: FastAPI) -> None:
    async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
        err = cast(DomainError, exc)
        return JSONResponse(status_code=err.status_code, content={"detail": err.detail})

    app.add_exception_handler(DomainError, handle_domain_error)
