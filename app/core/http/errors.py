import logging
from collections.abc import Mapping
from typing import Any, cast

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.error_codes import ErrorCode
from app.core.exceptions import DomainError, ErrorParams
from app.core.observability.request_context import REQUEST_ID_HEADER, get_request_id

logger = logging.getLogger(__name__)

VALIDATION_MESSAGE = "The request could not be validated."
HTTP_ERROR_DETAIL = "Request failed"
UNEXPECTED_MESSAGE = "Something went wrong on our side."
UNEXPECTED_DETAIL = "Internal server error"

STATUS_CODES: dict[int, ErrorCode] = {
    status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    status.HTTP_413_CONTENT_TOO_LARGE: ErrorCode.PAYLOAD_TOO_LARGE,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
}


def _scalar_context(ctx: Mapping[str, Any] | None) -> dict[str, str | int]:
    return {
        key: value
        for key, value in (ctx or {}).items()
        if isinstance(value, str | int) and not isinstance(value, bool)
    }


def _correlation_id(request: Request | None) -> str | None:
    state = getattr(request, "state", None)
    from_state = getattr(state, "request_id", None) if state is not None else None
    return from_state if isinstance(from_state, str) else get_request_id()


# The id goes on the header as well as in the body because the catch-all 500 is
# served by Starlette, above the middleware that would otherwise set it.
def error_response(
    request: Request | None = None,
    *,
    status_code: int,
    detail: Any,
    message: str,
    code: ErrorCode,
    params: ErrorParams | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    correlation_id = _correlation_id(request)
    sent = dict(headers or {})
    if correlation_id:
        sent[REQUEST_ID_HEADER] = correlation_id
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "message": message,
            "code": code.value,
            "params": dict(params or {}),
            "request_id": correlation_id,
        },
        headers=sent or None,
    )


def register_exception_handlers(app: FastAPI) -> None:
    async def handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
        err = cast(DomainError, exc)
        logger.warning(
            "Domain error serving %s %s with status %s",
            request.method,
            request.url.path,
            err.status_code,
        )
        return error_response(
            request,
            status_code=err.status_code,
            detail=err.detail,
            message=err.detail,
            code=err.code,
            params=err.params,
        )

    async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
        err = cast(RequestValidationError, exc)
        detail = [
            {
                "type": error["type"],
                "loc": list(error["loc"]),
                "msg": error["msg"],
                "ctx": _scalar_context(error.get("ctx")),
            }
            for error in err.errors()
        ]
        return error_response(
            request,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=detail,
            message=VALIDATION_MESSAGE,
            code=ErrorCode.VALIDATION,
        )

    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled error serving %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return error_response(
            request,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=UNEXPECTED_DETAIL,
            message=UNEXPECTED_MESSAGE,
            code=ErrorCode.UNEXPECTED,
        )

    # The 401 from the bearer scheme and the 404 for an unrouted path are
    # raised by the framework, and a client that has to special-case their
    # shape has lost the point of one envelope. FastAPI wraps anything raised
    # while it reads the body in a 400, so a domain error underneath one is
    # unwrapped and answered as itself.
    async def handle_http_error(request: Request, exc: Exception) -> JSONResponse:
        err = cast(StarletteHTTPException, exc)
        if isinstance(err.__cause__, DomainError):
            return await handle_domain_error(request, err.__cause__)
        detail = err.detail if isinstance(err.detail, str) else HTTP_ERROR_DETAIL
        return error_response(
            request,
            status_code=err.status_code,
            detail=detail,
            message=detail,
            code=STATUS_CODES.get(err.status_code, ErrorCode.REQUEST_FAILED),
            headers=err.headers,
        )

    app.add_exception_handler(StarletteHTTPException, handle_http_error)
    app.add_exception_handler(DomainError, handle_domain_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
