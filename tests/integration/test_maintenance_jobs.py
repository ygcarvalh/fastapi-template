from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.jobs.locking import held_by_one_replica, lock_key
from app.jobs.maintenance import (
    PRUNE_REQUEST_LOG,
    expire_tokens,
    once_across_replicas,
    prune_request_log,
)
from app.jobs.registry import maintenance_jobs
from app.models.refresh_token import RefreshToken
from app.models.request_log import RequestLog
from app.models.single_use_token import SingleUseToken, TokenPurpose
from app.models.user import User

PAST = datetime.now(UTC) - timedelta(days=400)
OWNER_EMAIL = "jobs@example.com"


@pytest_asyncio.fixture
async def factory(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    made = async_sessionmaker(engine, expire_on_commit=False)
    for module in ("app.jobs.maintenance",):
        monkeypatch.setattr(f"{module}.get_session_factory", lambda: made)

    yield made

    async with made() as session:
        for model in (RequestLog, RefreshToken, SingleUseToken):
            for row in (await session.execute(select(model))).scalars().all():
                await session.delete(row)
        await session.commit()


async def _forget(session: AsyncSession, user_id: int) -> None:
    for model in (RefreshToken, SingleUseToken):
        for row in (
            (await session.execute(select(model).where(model.user_id == user_id)))
            .scalars()
            .all()
        ):
            await session.delete(row)
    stored = await session.get(User, user_id)
    if stored is not None:
        await session.delete(stored)
    await session.commit()


@pytest_asyncio.fixture
async def owner(factory: async_sessionmaker[AsyncSession]) -> AsyncGenerator[int]:
    async with factory() as session:
        for stale in (
            (await session.execute(select(User).where(User.email == OWNER_EMAIL)))
            .scalars()
            .all()
        ):
            await _forget(session, stale.id)
        user = User(email=OWNER_EMAIL, hashed_password="x")
        session.add(user)
        await session.commit()
        user_id = int(user.id)

    yield user_id

    async with factory() as session:
        await _forget(session, user_id)


async def _count(factory: async_sessionmaker[AsyncSession], model: type) -> int:
    async with factory() as session:
        return int(
            (
                await session.execute(select(func.count()).select_from(model))
            ).scalar_one()
        )


async def test_pruning_drops_only_the_rows_that_aged_out(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async with factory() as session:
        old = RequestLog(
            request_id="old",
            method="GET",
            path="/old",
            status_code=200,
            duration_ms=1.0,
        )
        old.created_at = PAST
        session.add(old)
        session.add(
            RequestLog(
                request_id="new",
                method="GET",
                path="/new",
                status_code=200,
                duration_ms=1.0,
            )
        )
        await session.commit()

    removed = await prune_request_log(timedelta(days=30))

    assert removed == 1
    assert await _count(factory, RequestLog) == 1


async def test_expired_tokens_are_swept(
    factory: async_sessionmaker[AsyncSession], owner: int
) -> None:
    async with factory() as session:
        session.add(
            RefreshToken(
                token_hash="a" * 64,
                user_id=owner,
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        session.add(
            SingleUseToken(
                token_hash="b" * 64,
                user_id=owner,
                purpose=TokenPurpose.PASSWORD_RESET,
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        session.add(
            SingleUseToken(
                token_hash="c" * 64,
                user_id=owner,
                purpose=TokenPurpose.PASSWORD_RESET,
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        await session.commit()

    removed = await expire_tokens()

    assert removed == 2
    assert await _count(factory, SingleUseToken) == 1


async def test_a_second_replica_skips_work_the_first_is_doing(
    factory: async_sessionmaker[AsyncSession], engine: AsyncEngine
) -> None:
    ran: list[str] = []

    async def work() -> int:
        ran.append("first")
        async with (
            factory() as other,
            held_by_one_replica(other, PRUNE_REQUEST_LOG) as acquired,
        ):
            assert not acquired
        return 7

    assert await once_across_replicas(PRUNE_REQUEST_LOG, work) == 7
    assert ran == ["first"]


async def test_the_lock_is_handed_back_when_the_job_ends(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    async def work() -> int:
        return 1

    await once_across_replicas(PRUNE_REQUEST_LOG, work)

    async with (
        factory() as session,
        held_by_one_replica(session, PRUNE_REQUEST_LOG) as acquired,
    ):
        assert acquired


def test_every_maintenance_job_is_named_once() -> None:
    names = [job.name for job in maintenance_jobs(get_settings())]

    assert len(names) == len(set(names))
    assert names


def test_two_job_names_never_share_a_lock() -> None:
    keys = {lock_key(job.name) for job in maintenance_jobs(get_settings())}

    assert len(keys) == len(maintenance_jobs(get_settings()))
