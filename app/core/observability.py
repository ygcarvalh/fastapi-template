import time
from collections.abc import Iterable

import structlog
from fastapi import FastAPI, Request, Response

from app.core.middleware import CallNext
from app.core.request_context import (
    REQUEST_ID_HEADER,
    new_request_id,
    sanitize_request_id,
    set_request_id,
)

SERVER_ERROR_STATUS = 500

logger = structlog.stdlib.get_logger("app.request")


def parse_excluded_paths(raw: str) -> frozenset[str]:
    return frozenset(path.strip() for path in raw.split(",") if path.strip())


def _client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def _log_request(request: Request, *, status_code: int, started: float) -> None:
    event = {
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "client_ip": _client_ip(request),
        "user_id": getattr(request.state, "user_id", None),
    }
    if status_code >= SERVER_ERROR_STATUS:
        logger.warning("request", **event)
    else:
        logger.info("request", **event)


def register_request_logging(app: FastAPI, *, excluded_paths: Iterable[str]) -> None:
    excluded = frozenset(excluded_paths)

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
            _log_request(request, status_code=SERVER_ERROR_STATUS, started=started)
            raise

        response.headers[REQUEST_ID_HEADER] = request_id
        if request.url.path not in excluded:
            _log_request(request, status_code=response.status_code, started=started)
        return response
