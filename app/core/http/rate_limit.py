from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.error_codes import ErrorCode
from app.core.http.errors import error_response

RATE_LIMIT_DETAIL = "Too many requests"
RATE_LIMIT_MESSAGE = "Too many requests. Try again shortly."

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=get_settings().rate_limit_storage_uri or None,
)


def register_rate_limiting(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    async def handle_rate_limit_exceeded(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=429,
            detail=RATE_LIMIT_DETAIL,
            message=RATE_LIMIT_MESSAGE,
            code=ErrorCode.RATE_LIMITED,
        )

    app.add_exception_handler(RateLimitExceeded, handle_rate_limit_exceeded)


def reset_rate_limits() -> None:
    limiter.reset()
