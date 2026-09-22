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

limiter = Limiter(key_func=get_remote_address)


def register_rate_limiting(app: FastAPI) -> None:
    # slowapi has no public way to rebind a Limiter's storage after
    # construction (no `init_app`, unlike flask-limiter). Route decorators
    # such as `@limiter.limit(...)` run once, at import time, and register
    # themselves on this module-level singleton, so we keep it and only
    # replace its storage-related attributes here, rather than calling
    # `Limiter.__init__` again on it: that would also reset the per-route
    # limits the decorators already registered on it, since those routes are
    # never re-imported and so never re-decorated.
    #
    # A consequence: this mutates the shared module-level `limiter` in place,
    # so if two `create_app()`-built apps are alive at the same time in one
    # process, they share the exact same `Limiter` object and storage
    # backend, and whichever app was created most recently silently
    # reconfigures storage for every other still-alive app too. That's fine
    # for how this codebase actually runs it — one app per process in
    # production, and tests build apps one after another, not concurrently —
    # but would need a real per-app `Limiter` instance (and route decorators
    # reworked to look it up per request instead of closing over a module
    # singleton) if that usage pattern ever changes.
    reconfigured = Limiter(
        key_func=get_remote_address,
        storage_uri=get_settings().rate_limit_storage_uri or None,
    )
    limiter._storage_uri = reconfigured._storage_uri
    limiter._storage = reconfigured._storage
    limiter._limiter = reconfigured._limiter
    limiter._storage_dead = reconfigured._storage_dead
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
