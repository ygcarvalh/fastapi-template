from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response

HSTS_MAX_AGE_SECONDS = 31_536_000

STATIC_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}

CallNext = Callable[[Request], Awaitable[Response]]


def register_security_headers(app: FastAPI, *, hsts_enabled: bool) -> None:
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next: CallNext) -> Response:
        response = await call_next(request)
        for header, value in STATIC_SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        if hsts_enabled:
            response.headers.setdefault(
                "Strict-Transport-Security",
                f"max-age={HSTS_MAX_AGE_SECONDS}; includeSubDomains",
            )
        return response
