import json
import logging
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from typing import Any

import pytest
import structlog
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from structlog.testing import capture_logs

from app.core.observability.logging import configure_logging
from app.core.observability.request_context import REQUEST_ID_HEADER
from app.main import create_app


@pytest.fixture
def emitted(tmp_path: Path) -> Iterator[Path]:
    log_file = tmp_path / "api.jsonl"
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    config = structlog.get_config()
    configure_logging(
        level="INFO",
        json_format=True,
        service_name="fastapi-template",
        log_file=str(log_file),
    )
    try:
        yield log_file
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()
        for handler in handlers:
            root.addHandler(handler)
        root.setLevel(level)
        structlog.configure(**config)


def _requests(
    captured: list[MutableMapping[str, Any]],
) -> list[MutableMapping[str, Any]]:
    return [entry for entry in captured if entry["event"] == "request"]


def _emitted_requests(log_file: Path) -> list[dict[str, Any]]:
    lines = (
        json.loads(line)
        for line in log_file.read_text().splitlines()
        if line.startswith("{")
    )
    return [entry for entry in lines if entry.get("event") == "request"]


def _app_that_crashes() -> FastAPI:
    crashing = create_app()

    @crashing.get("/boom")
    async def boom() -> None:
        raise RuntimeError("the real cause")

    return crashing


async def test_one_line_describes_the_whole_request(client: AsyncClient) -> None:
    with capture_logs() as captured:
        await client.get("/api/v1/items", headers={REQUEST_ID_HEADER: "abc-123"})

    (entry,) = _requests(captured)
    assert entry["method"] == "GET"
    assert entry["path"] == "/api/v1/items"
    assert entry["status_code"] == 401
    assert entry["duration_ms"] >= 0
    assert entry["log_level"] == "info"


async def test_the_line_carries_the_authenticated_user(
    auth_client: AsyncClient,
) -> None:
    with capture_logs() as captured:
        await auth_client.get("/api/v1/items")

    (entry,) = _requests(captured)
    assert entry["status_code"] == 200
    assert isinstance(entry["user_id"], int)


async def test_excluded_paths_stay_quiet(client: AsyncClient) -> None:
    with capture_logs() as captured:
        await client.get("/health")

    assert _requests(captured) == []


async def test_a_crash_is_logged_at_warning() -> None:
    transport = ASGITransport(app=_app_that_crashes(), raise_app_exceptions=False)

    with capture_logs() as captured:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/boom")

    (entry,) = _requests(captured)
    assert response.status_code == 500
    assert entry["status_code"] == 500
    assert entry["log_level"] == "warning"


async def test_the_emitted_line_carries_the_request_id(
    client: AsyncClient, emitted: Path
) -> None:
    await client.get("/api/v1/items", headers={REQUEST_ID_HEADER: "abc-123"})

    (entry,) = _emitted_requests(emitted)
    assert entry["request_id"] == "abc-123"
    assert entry["service"] == "fastapi-template"
