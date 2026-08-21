import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.session import get_session
from app.models.user import User

COMMITTED_EMAIL = "commit-probe@example.com"
ROLLED_BACK_EMAIL = "rollback-probe@example.com"

SessionFactory = async_sessionmaker[AsyncSession]


@pytest.fixture
def bound_factory(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> SessionFactory:
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.db.session.get_session_factory", lambda: factory)
    return factory


async def _stored_count(factory: SessionFactory, email: str) -> int:
    async with factory() as session:
        found = await session.execute(select(User).where(User.email == email))
        return len(found.scalars().all())


async def _purge(factory: SessionFactory, email: str) -> None:
    async with factory() as session:
        await session.execute(delete(User).where(User.email == email))
        await session.commit()


async def test_get_session_commits_when_the_request_succeeds(
    bound_factory: SessionFactory,
) -> None:
    try:
        async for session in get_session():
            session.add(User(email=COMMITTED_EMAIL, hashed_password="x"))

        assert await _stored_count(bound_factory, COMMITTED_EMAIL) == 1
    finally:
        await _purge(bound_factory, COMMITTED_EMAIL)


async def test_get_session_rolls_back_when_the_request_raises(
    bound_factory: SessionFactory,
) -> None:
    sessions = get_session()
    session = await anext(sessions)
    session.add(User(email=ROLLED_BACK_EMAIL, hashed_password="x"))

    with pytest.raises(RuntimeError):
        await sessions.athrow(RuntimeError("request failed"))

    assert await _stored_count(bound_factory, ROLLED_BACK_EMAIL) == 0
