from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def register_rate_limiting(app: FastAPI) -> None:
    app.state.limiter = limiter
    app.add_middleware(SlowAPIMiddleware)

    async def handle_rate_limit_exceeded(
        request: Request, exc: Exception
    ) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests"},
        )

    app.add_exception_handler(RateLimitExceeded, handle_rate_limit_exceeded)


def reset_rate_limits() -> None:
    limiter.reset()
