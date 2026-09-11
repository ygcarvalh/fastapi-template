from fastapi import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import PayloadTooLargeError
from app.core.http.errors import error_response

BODY_TOO_LARGE_DETAIL = "Request body too large"
CONTENT_LENGTH_HEADER = b"content-length"


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope["headers"]:
        if name == CONTENT_LENGTH_HEADER:
            return int(value)
    return None


# A declared length is refused before the app runs. A body that arrives
# without one is counted as it streams and cut off where it passes the limit;
# that refusal surfaces from the read inside the route, so the exception
# handlers turn it into the same 413.
class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        declared = _declared_length(scope)
        if declared is not None and declared > self._max_bytes:
            await self._refuse(scope, receive, send)
            return
        await self._app(scope, self._bounded(receive), send)

    async def _refuse(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = error_response(
            Request(scope),
            status_code=PayloadTooLargeError.status_code,
            detail=BODY_TOO_LARGE_DETAIL,
            message=BODY_TOO_LARGE_DETAIL,
        )
        await response(scope, receive, send)

    def _bounded(self, receive: Receive) -> Receive:
        received = 0

        async def bounded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self._max_bytes:
                    raise PayloadTooLargeError(BODY_TOO_LARGE_DETAIL)
            return message

        return bounded_receive
