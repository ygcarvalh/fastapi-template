import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, Field

from app.core.exceptions import NotFoundError
from app.core.http.errors import (
    UNEXPECTED_DETAIL,
    UNEXPECTED_MESSAGE,
    VALIDATION_MESSAGE,
    register_exception_handlers,
)


def _app_raising(exc: Exception) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise exc

    return app


async def test_domain_error_maps_to_status() -> None:
    transport = ASGITransport(app=_app_raising(NotFoundError("nope")))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")
    assert response.status_code == 404
    assert response.json() == {
        "detail": "nope",
        "message": "nope",
        "request_id": None,
    }


async def test_unexpected_error_returns_a_generic_500() -> None:
    app = _app_raising(RuntimeError("connection string is postgres://u:hunter2@db"))
    transport = ASGITransport(app=app, raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "detail": UNEXPECTED_DETAIL,
        "message": UNEXPECTED_MESSAGE,
        "request_id": None,
    }
    assert "hunter2" not in response.text


async def test_unexpected_error_is_logged_with_its_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = _app_raising(RuntimeError("the real cause"))
    transport = ASGITransport(app=app, raise_app_exceptions=False)

    with caplog.at_level(logging.ERROR):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.get("/boom")

    assert any(record.exc_info for record in caplog.records)
    assert "the real cause" in caplog.text


async def test_validation_error_omits_the_submitted_value() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    class Payload(BaseModel):
        secret: str = Field(min_length=8)

    @app.post("/echo")
    async def echo(payload: Payload) -> None: ...

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/echo", json={"secret": "leaky"})

    assert response.status_code == 422
    assert "leaky" not in response.text
    body = response.json()
    assert body["detail"][0]["loc"] == ["body", "secret"]
    assert body["message"] == VALIDATION_MESSAGE
