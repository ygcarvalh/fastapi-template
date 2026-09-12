from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.policy import AuditAction
from app.models.audit_log import AuditLog
from app.models.item import Item
from app.models.role import Role
from app.models.user import User, UserRole

ADMIN_EMAIL = "remover@example.com"
TARGET_EMAIL = "removed@example.com"
PASSWORD = "secret123"

UserFactory = Callable[..., Awaitable[dict[str, Any]]]


async def _account(session: AsyncSession, email: str) -> User | None:
    return (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()


@pytest_asyncio.fixture
async def admin_client(
    client: AsyncClient, db_session: AsyncSession, user_factory: UserFactory
) -> AsyncGenerator[AsyncClient]:
    await user_factory(email="bootstrap@example.com", password=PASSWORD)
    await user_factory(email=ADMIN_EMAIL, password=PASSWORD)
    account = await _account(db_session, ADMIN_EMAIL)
    assert account is not None
    role = (
        await db_session.execute(select(Role).where(Role.name == UserRole.ADMIN))
    ).scalar_one()
    account.roles = [role]
    await db_session.flush()

    login = await client.post(
        "/api/v1/auth/login", data={"username": ADMIN_EMAIL, "password": PASSWORD}
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    yield client
    client.headers.pop("Authorization", None)


async def test_an_account_is_closed_and_stops_resolving(
    admin_client: AsyncClient, db_session: AsyncSession, user_factory: UserFactory
) -> None:
    target = await user_factory(email=TARGET_EMAIL, password=PASSWORD)

    removed = await admin_client.delete(f"/api/v1/users/{target['id']}")

    assert removed.status_code == 204
    assert (await admin_client.get(f"/api/v1/users/{target['id']}")).status_code == 404
    assert await _account(db_session, TARGET_EMAIL) is not None


async def test_what_the_account_owned_goes_with_it(
    admin_client: AsyncClient,
    client: AsyncClient,
    db_session: AsyncSession,
    user_factory: UserFactory,
) -> None:
    target = await user_factory(email=TARGET_EMAIL, password=PASSWORD)
    held = admin_client.headers.pop("Authorization")
    login = await client.post(
        "/api/v1/auth/login", data={"username": TARGET_EMAIL, "password": PASSWORD}
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    await client.post("/api/v1/items", json={"title": "theirs"})
    admin_client.headers["Authorization"] = held

    await admin_client.delete(f"/api/v1/users/{target['id']}")

    owned = (
        (await db_session.execute(select(Item).where(Item.owner_id == target["id"])))
        .scalars()
        .all()
    )
    assert [item.deleted_at is not None for item in owned] == [True]


async def test_the_closed_account_cannot_sign_in_again(
    admin_client: AsyncClient, client: AsyncClient, user_factory: UserFactory
) -> None:
    target = await user_factory(email=TARGET_EMAIL, password=PASSWORD)
    await admin_client.delete(f"/api/v1/users/{target['id']}")

    login = await client.post(
        "/api/v1/auth/login", data={"username": TARGET_EMAIL, "password": PASSWORD}
    )

    assert login.status_code == 401


async def test_closing_your_own_account_is_not_this_route(
    admin_client: AsyncClient, db_session: AsyncSession
) -> None:
    account = await _account(db_session, ADMIN_EMAIL)
    assert account is not None

    refused = await admin_client.delete(f"/api/v1/users/{account.id}")

    assert refused.status_code == 403


async def test_an_account_that_never_existed_is_not_found(
    admin_client: AsyncClient,
) -> None:
    assert (await admin_client.delete("/api/v1/users/999999")).status_code == 404


async def test_an_account_without_the_permission_is_refused(
    auth_client: AsyncClient,
) -> None:
    assert (await auth_client.delete("/api/v1/users/1")).status_code == 403


async def test_closing_an_account_reaches_the_trail(
    admin_client: AsyncClient, db_session: AsyncSession, user_factory: UserFactory
) -> None:
    target = await user_factory(email=TARGET_EMAIL, password=PASSWORD)
    await admin_client.delete(f"/api/v1/users/{target['id']}")

    recorded = (
        (
            await db_session.execute(
                select(AuditLog).where(
                    AuditLog.table_name == "users",
                    AuditLog.action == AuditAction.SOFT_DELETE,
                )
            )
        )
        .scalars()
        .all()
    )
    assert [entry.row_pk for entry in recorded] == [str(target["id"])]
