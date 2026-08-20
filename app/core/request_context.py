import re
from collections.abc import MutableMapping
from contextvars import ContextVar
from typing import Any
from uuid import uuid4

REQUEST_ID_HEADER = "X-Request-ID"
MAX_REQUEST_ID_LENGTH = 64

_REQUEST_ID_PATTERN = re.compile(rf"\A[A-Za-z0-9_-]{{1,{MAX_REQUEST_ID_LENGTH}}}\Z")

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    return uuid4().hex


def sanitize_request_id(value: str | None) -> str | None:
    if value is None or not _REQUEST_ID_PATTERN.match(value):
        return None
    return value


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()


def add_request_id(
    _logger: Any, _method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    request_id = get_request_id()
    if request_id is not None:
        event_dict["request_id"] = request_id
    return event_dict
