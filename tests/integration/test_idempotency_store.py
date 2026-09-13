import asyncio
from collections.abc import AsyncGenerator
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.idempotency_store import DatabaseIdempotencyStore
from app.models.idempotency_key import IdempotencyKey
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.idempotency import Attempt, ClaimState, StoredResponse
from app.services.idempotency_service import IdempotencyService

KEY = "store-001"
OWNER = 4242
ANSWER = StoredResponse(201, '{"id": 1}', "application/json")


@pytest_asyncio.fixture
async def store(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[DatabaseIdempotencyStore]:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        "app.api.idempotency_store.get_session_factory", lambda: factory
    )

    yield DatabaseIdempotencyStore()

    async with factory() as session:
        await session.execute(
            delete(IdempotencyKey).where(IdempotencyKey.user_id == OWNER)
        )
        await session.commit()


def _attempt(body: bytes = b'{"title": "one"}') -> Attempt:
    return Attempt(OWNER, KEY, "POST", "/api/v1/items", body)


async def test_a_claim_survives_its_own_transaction(
    store: DatabaseIdempotencyStore,
) -> None:
    first = await store.claim(_attempt())
    second = await store.claim(_attempt())

    assert first.state is ClaimState.FRESH
    assert second.state is ClaimState.IN_FLIGHT


async def test_a_completed_claim_replays_across_connections(
    store: DatabaseIdempotencyStore,
) -> None:
    await store.claim(_attempt())

    await store.complete(OWNER, KEY, ANSWER)
    claim = await store.claim(_attempt())

    assert claim.state is ClaimState.REPLAY
    assert claim.stored == ANSWER


async def test_two_callers_racing_the_same_key_leave_one_winner(
    store: DatabaseIdempotencyStore,
) -> None:
    claims = await asyncio.gather(store.claim(_attempt()), store.claim(_attempt()))

    assert sorted(claim.state for claim in claims) == [
        ClaimState.FRESH,
        ClaimState.IN_FLIGHT,
    ]


async def test_a_released_claim_frees_the_key(
    store: DatabaseIdempotencyStore,
) -> None:
    await store.claim(_attempt())

    await store.release(OWNER, KEY)

    assert (await store.claim(_attempt())).state is ClaimState.FRESH


async def test_pruning_removes_what_aged_out(
    store: DatabaseIdempotencyStore, engine: AsyncEngine
) -> None:
    await store.claim(_attempt())

    async with AsyncSession(bind=engine, expire_on_commit=False) as session:
        service = IdempotencyService(IdempotencyRepository(session))
        dropped = await service.prune_batch(timedelta(seconds=-1), 100)
        await session.commit()

    assert dropped == 1
    assert (await store.claim(_attempt())).state is ClaimState.FRESH
