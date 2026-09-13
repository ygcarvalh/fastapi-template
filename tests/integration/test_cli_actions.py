from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.cli import actions
from app.core.exceptions import ConflictError, NotFoundError
from app.core.security import verify_password
from app.models.user import User, UserRole

EMAIL = "founder@example.com"
PASSWORD = "a-long-enough-secret"


@pytest_asyncio.fixture
async def factory(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    made = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.cli.actions.get_session_factory", lambda: made)

    yield made

    async with made() as session:
        for row in (
            (await session.execute(select(User).where(User.email == EMAIL)))
            .scalars()
            .all()
        ):
            await session.delete(row)
        await session.commit()


async def _stored(factory: async_sessionmaker[AsyncSession]) -> User:
    async with factory() as session:
        return (
            await session.execute(select(User).where(User.email == EMAIL))
        ).scalar_one()


async def test_creating_a_superuser_hashes_the_password(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.create_superuser(EMAIL, PASSWORD)

    user = await _stored(factory)
    assert user.hashed_password != PASSWORD
    assert verify_password(PASSWORD, user.hashed_password)


async def test_a_superuser_holds_the_administrator_role(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.create_superuser(EMAIL, PASSWORD)

    user = await _stored(factory)
    assert [role.name for role in user.roles] == [UserRole.ADMIN]


async def test_a_superuser_starts_confirmed(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.create_superuser(EMAIL, PASSWORD)

    assert (await _stored(factory)).email_verified_at is not None


async def test_the_address_is_stored_the_way_the_api_stores_it(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.create_superuser(EMAIL.upper(), PASSWORD)

    assert (await _stored(factory)).email == EMAIL


async def test_creating_the_same_account_twice_is_refused(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.create_superuser(EMAIL, PASSWORD)

    with pytest.raises(ConflictError):
        await actions.create_superuser(EMAIL, PASSWORD)


async def test_granting_a_role_nobody_defined_is_refused(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.create_superuser(EMAIL, PASSWORD)

    with pytest.raises(NotFoundError):
        await actions.grant_role(EMAIL, "invented")


async def test_granting_a_role_to_an_unknown_account_is_refused(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(NotFoundError):
        await actions.grant_role("stranger@example.com", UserRole.USER)


async def test_granting_a_role_twice_changes_nothing(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.create_superuser(EMAIL, PASSWORD)

    first = await actions.grant_role(EMAIL, UserRole.USER)
    second = await actions.grant_role(EMAIL, UserRole.USER)

    assert "now holds" in first
    assert "already holds" in second
    user = await _stored(factory)
    assert sorted(role.name for role in user.roles) == [UserRole.ADMIN, UserRole.USER]


async def test_seeding_a_database_that_already_has_roles_is_a_no_op(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    assert await actions.seed() == "roles are already seeded"


async def test_confirming_an_unknown_address_is_refused(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(NotFoundError):
        await actions.verify_email("stranger@example.com")
