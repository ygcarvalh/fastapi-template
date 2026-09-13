from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.core.http.idempotency import IDEMPOTENCY_KEY_HEADER, REPLAY_HEADER
from app.models.idempotency_key import IdempotencyKey

KEY = {IDEMPOTENCY_KEY_HEADER: "route-001"}


@pytest_asyncio.fixture(autouse=True)
async def real_store(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[None]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        "app.api.idempotency_store.get_session_factory", lambda: factory
    )

    yield

    async with factory() as session:
        await session.execute(delete(IdempotencyKey))
        await session.commit()


async def test_a_retried_creation_makes_one_item(auth_client: AsyncClient) -> None:
    payload = {"title": "only once"}

    first = await auth_client.post("/api/v1/items", json=payload, headers=KEY)
    second = await auth_client.post("/api/v1/items", json=payload, headers=KEY)

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert second.headers[REPLAY_HEADER] == "true"
    listing = await auth_client.get("/api/v1/items")
    assert listing.json()["total"] == 1


async def test_the_same_key_on_a_different_body_is_refused(
    auth_client: AsyncClient,
) -> None:
    await auth_client.post("/api/v1/items", json={"title": "one"}, headers=KEY)

    response = await auth_client.post(
        "/api/v1/items", json={"title": "two"}, headers=KEY
    )

    assert response.status_code == 409
    assert response.json()["code"] == "idempotency.bodyMismatch"
    listing = await auth_client.get("/api/v1/items")
    assert listing.json()["total"] == 1


async def test_a_creation_without_a_key_still_repeats(
    auth_client: AsyncClient,
) -> None:
    await auth_client.post("/api/v1/items", json={"title": "twice"})
    await auth_client.post("/api/v1/items", json={"title": "twice"})

    listing = await auth_client.get("/api/v1/items")
    assert listing.json()["total"] == 2
