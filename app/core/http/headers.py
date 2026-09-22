from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

HSTS_MAX_AGE_SECONDS = 31_536_000

STATIC_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts_enabled: bool) -> None:
        self._app = app
        self._hsts_enabled = hsts_enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        await self._app(scope, receive, self._wrapped(send))

    def _wrapped(self, send: Send) -> Send:
        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=message["headers"])
                for header, value in STATIC_SECURITY_HEADERS.items():
                    headers.setdefault(header, value)
                if self._hsts_enabled:
                    headers.setdefault(
                        "Strict-Transport-Security",
                        f"max-age={HSTS_MAX_AGE_SECONDS}; includeSubDomains",
                    )
            await send(message)

        return wrapped_send


def register_security_headers(app: FastAPI, *, hsts_enabled: bool) -> None:
    app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=hsts_enabled)
