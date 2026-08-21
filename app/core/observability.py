import time
from collections.abc import Iterable

import structlog
from fastapi import FastAPI, Request, Response
from starlette.background import BackgroundTask, BackgroundTasks

from app.core.middleware import CallNext
from app.core.request_context import (
    REQUEST_ID_HEADER,
    new_request_id,
    sanitize_request_id,
    set_request_id,
)
from app.core.request_recorder import RequestRecorder
from app.schemas.request_log import RequestRecord

SERVER_ERROR_STATUS = 500

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


def _after_response(response: Response, task: BackgroundTask) -> None:
    running = response.background
    if running is None:
        response.background = task
        return
    response.background = BackgroundTasks([running, task])


def register_request_logging(
    app: FastAPI,
    *,
    excluded_paths: Iterable[str],
    recorder: RequestRecorder | None = None,
) -> None:
    excluded = frozenset(excluded_paths)

    async def persist(record: RequestRecord) -> None:
        if recorder is None:
            return
        try:
            await recorder(record)
        except Exception:
            # An audit row must never turn a served response into a 500.
            logger.warning("request_log_write_failed", exc_info=True)

    @app.middleware("http")
    async def log_request(request: Request, call_next: CallNext) -> Response:
        structlog.contextvars.clear_contextvars()
        inbound = sanitize_request_id(request.headers.get(REQUEST_ID_HEADER))
        request_id = inbound or new_request_id()
        set_request_id(request_id)
        request.state.request_id = request_id

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            record = _record(
                request,
                request_id=request_id,
                status_code=SERVER_ERROR_STATUS,
                started=started,
            )
            _log_request(record)
            await persist(record)
            raise

        response.headers[REQUEST_ID_HEADER] = request_id
        if request.url.path not in excluded:
            record = _record(
                request,
                request_id=request_id,
                status_code=response.status_code,
                started=started,
            )
            _log_request(record)
            if recorder is not None:
                # After the body is sent, so the caller waits for nothing and
                # the request's own connection is already back in the pool.
                _after_response(response, BackgroundTask(persist, record))
        return response
