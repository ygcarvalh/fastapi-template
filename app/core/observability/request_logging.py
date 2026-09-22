import time
from collections.abc import Awaitable, Callable, Iterable

import structlog
from fastapi import FastAPI, Request
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.audit.context import AuditContext, set_audit_context
from app.core.observability.request_context import (
    REQUEST_ID_HEADER,
    new_request_id,
    sanitize_request_id,
    set_request_id,
)
from app.schemas.request_log import RequestRecord

SERVER_ERROR_STATUS = 500

RequestRecorder = Callable[[RequestRecord], Awaitable[None]]

logger = structlog.stdlib.get_logger("app.request")


def parse_excluded_paths(raw: str) -> frozenset[str]:
    return frozenset(path.strip() for path in raw.split(",") if path.strip())


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 3)


def _record(
    request: Request, *, request_id: str, status_code: int, started: float
) -> RequestRecord:
    return RequestRecord(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=status_code,
        duration_ms=_elapsed_ms(started),
        client_ip=_client_ip(request),
        user_id=getattr(request.state, "user_id", None),
    )


def _log_request(record: RequestRecord) -> None:
    event = record.model_dump(exclude={"request_id"})
    if record.status_code >= SERVER_ERROR_STATUS:
        logger.warning("request", **event)
    else:
        logger.info("request", **event)


def _audit_context_for(request: Request, request_id: str) -> AuditContext:
    return AuditContext(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=_client_ip(request),
    )


class _ResponseCapture:
    def __init__(self, send: Send, *, request_id: str) -> None:
        self._send = send
        self._request_id = request_id
        self.status_code = SERVER_ERROR_STATUS

    async def __call__(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.status_code = message["status"]
            headers = MutableHeaders(raw=message["headers"])
            headers[REQUEST_ID_HEADER] = self._request_id
        await self._send(message)


class RequestLoggingMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        excluded_paths: Iterable[str],
        recorder: RequestRecorder | None = None,
    ) -> None:
        self._app = app
        self._excluded = frozenset(excluded_paths)
        self._recorder = recorder

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        structlog.contextvars.clear_contextvars()
        request = Request(scope, receive)
        inbound = sanitize_request_id(request.headers.get(REQUEST_ID_HEADER))
        request_id = inbound or new_request_id()
        set_request_id(request_id)
        request.state.request_id = request_id
        set_audit_context(_audit_context_for(request, request_id))

        started = time.perf_counter()
        capture = _ResponseCapture(send, request_id=request_id)
        try:
            await self._app(scope, receive, capture)
        except Exception:
            record = _record(
                request,
                request_id=request_id,
                status_code=SERVER_ERROR_STATUS,
                started=started,
            )
            _log_request(record)
            await self._persist(record)
            raise
        finally:
            set_audit_context(None)

        if request.url.path not in self._excluded:
            record = _record(
                request,
                request_id=request_id,
                status_code=capture.status_code,
                started=started,
            )
            _log_request(record)
            # After the body is sent, so the client already has its response;
            # only this coroutine's own return is delayed by the write.
            await self._persist(record)

    async def _persist(self, record: RequestRecord) -> None:
        if self._recorder is None:
            return
        try:
            await self._recorder(record)
        except Exception:
            # An audit row must never turn a served response into a 500.
            logger.warning("request_log_write_failed", exc_info=True)


def register_request_logging(
    app: FastAPI,
    *,
    excluded_paths: Iterable[str],
    recorder: RequestRecorder | None = None,
) -> None:
    app.add_middleware(
        RequestLoggingMiddleware, excluded_paths=excluded_paths, recorder=recorder
    )
