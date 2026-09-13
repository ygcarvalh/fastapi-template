from typing import Any

import pytest
from fastapi import FastAPI, Request, status
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel

from app.core.http.idempotency import (
    IDEMPOTENCY_KEY_HEADER,
    MAX_KEY_LENGTH,
    REPLAY_HEADER,
    IdempotencyMiddleware,
)
from app.schemas.idempotency import Attempt, Claim, StoredResponse
from app.services.idempotency_service import IdempotencyService
from tests.unit.fakes import FakeIdempotencyRepository

CALLER_ID = 42
KEY = {IDEMPOTENCY_KEY_HEADER: "key-001"}


class FakeStore:
    def __init__(self) -> None:
        self._service = IdempotencyService(FakeIdempotencyRepository())

    async def claim(self, attempt: Attempt) -> Claim:
        return await self._service.claim(attempt)

    async def complete(self, user_id: int, key: str, response: StoredResponse) -> None:
        await self._service.complete(user_id, key, response)

    async def release(self, user_id: int, key: str) -> None:
        await self._service.release(user_id, key)


class Payload(BaseModel):
    title: str


def _app(*, anonymous: bool = False) -> tuple[FastAPI, list[str]]:
    app = FastAPI()
    served: list[str] = []

    def caller_of(_: Request) -> int | None:
        return None if anonymous else CALLER_ID

    app.add_middleware(IdempotencyMiddleware, store=FakeStore(), caller_of=caller_of)

    @app.post("/things", status_code=status.HTTP_201_CREATED)
    async def create(payload: Payload) -> dict[str, Any]:
        served.append(payload.title)
        return {"id": len(served), "title": payload.title}

    @app.post("/refused", status_code=status.HTTP_400_BAD_REQUEST)
    async def refused() -> dict[str, str]:
        served.append("refused")
        return {"detail": "no"}

    @app.post("/boom")
    async def boom() -> None:
        served.append("boom")
        raise RuntimeError("the real cause")

    @app.post("/empty", status_code=status.HTTP_204_NO_CONTENT)
    async def empty() -> None:
        served.append("empty")

    @app.get("/things")
    async def read() -> dict[str, int]:
        served.append("read")
        return {"count": len(served)}

    return app, served


async def _client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_without_a_key_every_call_runs() -> None:
    app, served = _app()

    async with await _client(app) as client:
        await client.post("/things", json={"title": "one"})
        await client.post("/things", json={"title": "one"})

    assert served == ["one", "one"]


async def test_the_same_key_runs_once_and_replays_the_answer() -> None:
    app, served = _app()

    async with await _client(app) as client:
        first = await client.post("/things", json={"title": "one"}, headers=KEY)
        second = await client.post("/things", json={"title": "one"}, headers=KEY)

    assert served == ["one"]
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert REPLAY_HEADER not in first.headers
    assert second.headers[REPLAY_HEADER] == "true"


async def test_the_same_key_with_another_body_is_refused() -> None:
    app, served = _app()

    async with await _client(app) as client:
        await client.post("/things", json={"title": "one"}, headers=KEY)
        response = await client.post("/things", json={"title": "two"}, headers=KEY)

    assert served == ["one"]
    assert response.status_code == 409
    assert response.json()["code"] == "idempotency.bodyMismatch"


async def test_an_anonymous_caller_cannot_reserve_a_key() -> None:
    app, served = _app(anonymous=True)

    async with await _client(app) as client:
        await client.post("/things", json={"title": "one"}, headers=KEY)
        await client.post("/things", json={"title": "one"}, headers=KEY)

    assert served == ["one", "one"]


@pytest.mark.parametrize("key", ["", "x" * (MAX_KEY_LENGTH + 1), "with space"])
async def test_a_key_this_api_will_not_store_is_refused(key: str) -> None:
    app, served = _app()

    async with await _client(app) as client:
        response = await client.post(
            "/things", json={"title": "one"}, headers={IDEMPOTENCY_KEY_HEADER: key}
        )

    assert response.status_code == 400
    assert response.json()["code"] == "idempotency.invalidKey"
    assert served == []


async def test_a_refused_call_leaves_the_key_free_to_retry() -> None:
    app, served = _app()

    async with await _client(app) as client:
        await client.post("/refused", headers=KEY)
        await client.post("/refused", headers=KEY)

    assert served == ["refused", "refused"]


async def test_a_crash_leaves_the_key_free_to_retry() -> None:
    app, served = _app()

    async with await _client(app) as client:
        await client.post("/boom", headers=KEY)
        await client.post("/boom", headers=KEY)

    assert served == ["boom", "boom"]


async def test_an_empty_answer_replays_as_itself() -> None:
    app, served = _app()

    async with await _client(app) as client:
        first = await client.post("/empty", headers=KEY)
        second = await client.post("/empty", headers=KEY)

    assert served == ["empty"]
    assert first.status_code == second.status_code == 204
    assert second.headers[REPLAY_HEADER] == "true"


async def test_a_read_is_never_held_against_a_key() -> None:
    app, served = _app()

    async with await _client(app) as client:
        await client.get("/things", headers=KEY)
        await client.get("/things", headers=KEY)

    assert served == ["read", "read"]
