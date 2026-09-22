import logging
import string
from collections.abc import Callable
from typing import Protocol

from fastapi import Request, Response, status
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.error_codes import ErrorCode
from app.core.exceptions import PayloadTooLargeError
from app.core.http.body_limit import BODY_TOO_LARGE_DETAIL
from app.core.http.errors import error_response
from app.schemas.idempotency import Attempt, Claim, ClaimState, StoredResponse

logger = logging.getLogger(__name__)

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
REPLAY_HEADER = "Idempotent-Replay"
MAX_KEY_LENGTH = 255
MAX_STORED_BODY_BYTES = 64 * 1024
IDEMPOTENT_METHODS = frozenset({"POST", "PATCH", "PUT", "DELETE"})
JSON_CONTENT_TYPE = "application/json"
PRINTABLE = frozenset(string.printable) - frozenset(string.whitespace)

INVALID_KEY = "Idempotency-Key must be 1 to 255 printable characters"
BODY_MISMATCH = "This Idempotency-Key was already used with a different request"
IN_FLIGHT = "A request with this Idempotency-Key is still running"

CallerResolver = Callable[[Request], int | None]


class IdempotencyStore(Protocol):
    async def claim(self, attempt: Attempt) -> Claim: ...

    async def complete(
        self, user_id: int, key: str, response: StoredResponse
    ) -> None: ...

    async def release(self, user_id: int, key: str) -> None: ...


def is_valid_key(key: str) -> bool:
    return 0 < len(key) <= MAX_KEY_LENGTH and set(key) <= PRINTABLE


class _CapturedResponse:
    def __init__(self, send: Send) -> None:
        self._send = send
        self.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
        self.content_type: str | None = None
        self._chunks: list[bytes] = []

    async def __call__(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.status_code = message["status"]
            self.content_type = self._content_type(message.get("headers", []))
        elif message["type"] == "http.response.body":
            self._chunks.append(message.get("body", b""))
        await self._send(message)

    @property
    def body(self) -> bytes:
        return b"".join(self._chunks)

    @staticmethod
    def _content_type(headers: list[tuple[bytes, bytes]]) -> str | None:
        for name, value in headers:
            if name.lower() == b"content-type":
                return value.decode("latin-1")
        return None


class IdempotencyMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        store: IdempotencyStore,
        caller_of: CallerResolver,
        enabled: bool = True,
    ) -> None:
        self._app = app
        self._store = store
        self._caller_of = caller_of
        self._enabled = enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._enabled:
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive)
        key = request.headers.get(IDEMPOTENCY_KEY_HEADER)
        if key is None or request.method not in IDEMPOTENT_METHODS:
            await self._app(scope, receive, send)
            return

        if not is_valid_key(key):
            await self._refuse(
                request,
                scope,
                receive,
                send,
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=INVALID_KEY,
                code=ErrorCode.IDEMPOTENCY_INVALID_KEY,
            )
            return

        caller = self._caller_of(request)
        if caller is None:
            await self._app(scope, receive, send)
            return

        try:
            body = await request.body()
        except PayloadTooLargeError:
            await self._refuse(
                request,
                scope,
                receive,
                send,
                status_code=PayloadTooLargeError.status_code,
                detail=BODY_TOO_LARGE_DETAIL,
                code=ErrorCode.PAYLOAD_TOO_LARGE,
            )
            return
        attempt = Attempt(caller, key, request.method, request.url.path, body)
        claim = await self._store.claim(attempt)

        if claim.state is ClaimState.REPLAY and claim.stored is not None:
            await self._replay(claim.stored, scope, receive, send)
            return
        if claim.state is ClaimState.MISMATCH:
            await self._refuse(
                request,
                scope,
                receive,
                send,
                status_code=status.HTTP_409_CONFLICT,
                detail=BODY_MISMATCH,
                code=ErrorCode.IDEMPOTENCY_BODY_MISMATCH,
            )
            return
        if claim.state is ClaimState.IN_FLIGHT:
            await self._refuse(
                request,
                scope,
                receive,
                send,
                status_code=status.HTTP_409_CONFLICT,
                detail=IN_FLIGHT,
                code=ErrorCode.IDEMPOTENCY_IN_FLIGHT,
            )
            return

        await self._run(attempt, scope, self._buffered(body, receive), send)

    async def _run(
        self, attempt: Attempt, scope: Scope, receive: Receive, send: Send
    ) -> None:
        captured = _CapturedResponse(send)
        try:
            await self._app(scope, receive, captured)
        except Exception:
            await self._forget(attempt)
            raise
        await self._remember(attempt, captured)

    async def _remember(self, attempt: Attempt, captured: _CapturedResponse) -> None:
        if not self._storable(captured):
            await self._forget(attempt)
            return
        try:
            await self._store.complete(
                attempt.user_id,
                attempt.key,
                StoredResponse(
                    captured.status_code,
                    captured.body.decode(),
                    captured.content_type,
                ),
            )
        except Exception:
            logger.warning("idempotency_record_failed", exc_info=True)

    async def _forget(self, attempt: Attempt) -> None:
        try:
            await self._store.release(attempt.user_id, attempt.key)
        except Exception:
            logger.warning("idempotency_release_failed", exc_info=True)

    @staticmethod
    def _storable(captured: _CapturedResponse) -> bool:
        if (
            not status.HTTP_200_OK
            <= captured.status_code
            < status.HTTP_300_MULTIPLE_CHOICES
        ):
            return False
        if len(captured.body) > MAX_STORED_BODY_BYTES:
            return False
        if not captured.body:
            return True
        return (captured.content_type or "").startswith(JSON_CONTENT_TYPE)

    @staticmethod
    def _buffered(body: bytes, receive: Receive) -> Receive:
        replayed = False

        async def buffered_receive() -> Message:
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        return buffered_receive

    @staticmethod
    async def _replay(
        stored: StoredResponse, scope: Scope, receive: Receive, send: Send
    ) -> None:
        response = Response(
            content=stored.body,
            status_code=stored.status_code,
            media_type=stored.content_type,
            headers={REPLAY_HEADER: "true"},
        )
        await response(scope, receive, send)

    @staticmethod
    async def _refuse(
        request: Request,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        status_code: int,
        detail: str,
        code: ErrorCode,
    ) -> None:
        response = error_response(
            request,
            status_code=status_code,
            detail=detail,
            message=detail,
            code=code,
        )
        await response(scope, receive, send)
