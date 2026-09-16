from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.cli import actions
from app.core.audit.context import audit_suppressed
from app.core.config import get_settings
from app.core.security import verify_password
from app.db.demo import DEMO_PASSWORD, DEMO_USERS
from app.models.attachment import Attachment
from app.models.item import Item
from app.models.user import User, UserRole
from app.models.user_preferences import UserPreferences


@pytest_asyncio.fixture
async def factory(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[async_sessionmaker[AsyncSession]]:
    made = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.cli.actions.get_session_factory", lambda: made)

    yield made

    async with made() as session:
        with audit_suppressed():
            users = (
                (
                    await session.execute(
                        select(User).where(
                            User.email.in_([u.email for u in DEMO_USERS])
                        )
                    )
                )
                .scalars()
                .all()
            )
            for user in users:
                preferences = (
                    await session.execute(
                        select(UserPreferences).where(
                            UserPreferences.user_id == user.id
                        )
                    )
                ).scalar_one_or_none()
                if preferences is not None:
                    await session.delete(preferences)
                await session.delete(user)
            await session.commit()


async def _users(factory: async_sessionmaker[AsyncSession]) -> list[User]:
    async with factory() as session:
        return list(
            (
                await session.execute(
                    select(User).where(User.email.in_([u.email for u in DEMO_USERS]))
                )
            )
            .scalars()
            .all()
        )


async def test_every_demo_account_logs_in_with_the_documented_password(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.demo_seed()

    for user in await _users(factory):
        assert verify_password(DEMO_PASSWORD, user.hashed_password)


async def test_the_admin_account_holds_the_administrator_role(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.demo_seed()

    admin = next(u for u in await _users(factory) if u.email == "admin@example.com")
    assert [role.name for role in admin.roles] == [UserRole.ADMIN]


async def test_the_other_demo_accounts_hold_the_user_role(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.demo_seed()

    others = [u for u in await _users(factory) if u.email != "admin@example.com"]
    assert others
    for user in others:
        assert [role.name for role in user.roles] == [UserRole.USER]


async def test_carol_is_not_verified(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.demo_seed()

    carol = next(u for u in await _users(factory) if u.email == "carol@example.com")
    assert carol.email_verified_at is None


async def test_alice_and_bob_are_verified(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.demo_seed()

    for email in ("alice@example.com", "bob@example.com"):
        user = next(u for u in await _users(factory) if u.email == email)
        assert user.email_verified_at is not None


async def test_refuses_when_the_database_already_has_an_account(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.demo_seed()
    first_run_ids = sorted(user.id for user in await _users(factory))

    message = await actions.demo_seed()

    assert message == "the database already has accounts; demo data was not written"
    assert sorted(user.id for user in await _users(factory)) == first_run_ids


async def test_if_enabled_is_a_no_op_when_the_flag_is_off(
    factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_DATA_ENABLED", "false")
    get_settings.cache_clear()

    message = await actions.demo_seed(if_enabled=True)

    assert message == "demo data is turned off"
    assert await _users(factory) == []
    get_settings.cache_clear()


async def test_if_enabled_seeds_when_the_flag_is_on(
    factory: async_sessionmaker[AsyncSession], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEMO_DATA_ENABLED", "true")
    get_settings.cache_clear()

    message = await actions.demo_seed(if_enabled=True)

    assert "seeded" in message
    assert await _users(factory)
    get_settings.cache_clear()


async def test_alices_soft_deleted_item_is_excluded_from_active_items(
    factory: async_sessionmaker[AsyncSession],
) -> None:
    await actions.demo_seed()

    alice = next(u for u in await _users(factory) if u.email == "alice@example.com")
    async with factory() as session:
        active_titles = (
            (
                await session.execute(
                    select(Item.title).where(
                        Item.owner_id == alice.id, Item.is_active()
                    )
                )
            )
            .scalars()
            .all()
        )

    assert "Retired planning doc" not in active_titles
    assert "Draft the onboarding guide" in active_titles


async def test_alices_attachment_is_stored_and_readable(
    factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("STORAGE_ROOT", str(tmp_path))
    get_settings.cache_clear()

    await actions.demo_seed()

    alice = next(u for u in await _users(factory) if u.email == "alice@example.com")
    async with factory() as session:
        attachment = (
            await session.execute(
                select(Attachment)
                .join(Item, Attachment.item_id == Item.id)
                .where(Item.owner_id == alice.id)
            )
        ).scalar_one()

    stored = tmp_path / f"demo/{attachment.item_id}/{attachment.filename}"
    assert stored.read_bytes() == b"Remember to mention the DEMO_DATA_ENABLED flag.\n"
    assert stored.stat().st_size == attachment.size_bytes

    get_settings.cache_clear()
