import logging
import sys
from collections.abc import MutableMapping
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog

from app.core.observability.request_context import add_request_id

LOG_FILE_MAX_BYTES = 10 * 1024 * 1024
LOG_FILE_BACKUP_COUNT = 3

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

Processor = structlog.typing.Processor


def _add_service(service_name: str) -> Processor:
    def processor(
        _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        event_dict["service"] = service_name
        return event_dict

    return processor


def _shared_processors(service_name: str) -> list[Processor]:
    return [
        structlog.contextvars.merge_contextvars,
        add_request_id,
        _add_service(service_name),
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]


def _build_formatter(
    *, json_format: bool, shared: list[Processor]
) -> structlog.stdlib.ProcessorFormatter:
    renderer: Any
    tail: list[Any]
    if json_format:
        renderer = structlog.processors.JSONRenderer()
        tail = [structlog.processors.format_exc_info, renderer]
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
        tail = [renderer]
    return structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=list(shared),
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *tail,
        ],
    )


def _file_handler(log_file: str, formatter: logging.Formatter) -> logging.Handler:
    path = Path(log_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        path,
        maxBytes=LOG_FILE_MAX_BYTES,
        backupCount=LOG_FILE_BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    return handler


def configure_logging(
    *,
    level: str,
    json_format: bool,
    service_name: str,
    log_file: str | None = None,
) -> None:
    shared = _shared_processors(service_name)
    structlog.configure(
        processors=[
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    formatter = _build_formatter(json_format=json_format, shared=shared)
    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)

    handlers: list[logging.Handler] = [stream]
    if log_file:
        handlers.append(
            _file_handler(log_file, _build_formatter(json_format=True, shared=shared))
        )

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
        existing.close()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level.upper())

    for name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
