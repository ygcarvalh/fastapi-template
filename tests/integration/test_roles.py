from collections.abc import AsyncGenerator, Awaitable, Callable

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Role
from app.models.user import User, UserRole

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "secret123"


@pytest_asyncio.fixture
async def admin_client(
    client: AsyncClient,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> AsyncGenerator[AsyncClient]:
    await user_factory(email=ADMIN_EMAIL, password=ADMIN_PASSWORD)
    stored = await db_session.execute(select(User).where(User.email == ADMIN_EMAIL))
    admin_role = (
        await db_session.execute(select(Role).where(Role.name == UserRole.ADMIN))
    ).scalar_one()
    stored.scalar_one().role = admin_role
    await db_session.flush()

    login = await client.post(
        "/api/v1/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    token = login.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
    client.headers.pop("Authorization", None)


async def test_the_first_account_of_a_deployment_is_an_administrator(
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/api/v1/users", json={"email": "founder@example.com", "password": "secret123"}
    )

    assert created.json()["role"] == "superadmin"


async def test_later_accounts_are_not_administrators(
    client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    await user_factory(email="founder@example.com", password="secret123")

    created = await client.post(
        "/api/v1/users", json={"email": "plain@example.com", "password": "secret123"}
    )

    assert created.json()["role"] == "user"


async def test_listing_users_requires_the_admin_role(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/users")

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


async def test_listing_users_is_allowed_for_administrators(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.get("/api/v1/users")

    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert any(item["email"] == ADMIN_EMAIL for item in body["items"])


async def test_listing_users_still_requires_a_token(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/users")).status_code == 401


async def test_an_administrator_reads_another_account(
    admin_client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    other = await user_factory(email="other@example.com", password="secret123")

    response = await admin_client.get(f"/api/v1/users/{other['id']}")

    assert response.status_code == 200
    assert response.json()["email"] == "other@example.com"


async def test_reading_another_account_requires_the_admin_role(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get("/api/v1/users/1")

    assert response.status_code == 403


async def test_reading_an_account_that_is_not_there_is_a_404(
    admin_client: AsyncClient,
) -> None:
    assert (await admin_client.get("/api/v1/users/404")).status_code == 404


async def test_an_administrator_promotes_another_account(
    admin_client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    other = await user_factory(email="other@example.com", password="secret123")

    response = await admin_client.patch(
        f"/api/v1/users/{other['id']}/role", json={"role": "superadmin"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "superadmin"


async def test_an_administrator_cannot_change_their_own_role(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    stored = await db_session.execute(select(User).where(User.email == ADMIN_EMAIL))
    admin_id = stored.scalar_one().id

    response = await admin_client.patch(
        f"/api/v1/users/{admin_id}/role", json={"role": "user"}
    )

    assert response.status_code == 403


async def test_changing_a_role_requires_the_admin_role(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.patch("/api/v1/users/1/role", json={"role": "superadmin"})

    assert response.status_code == 403


async def test_an_administrator_reads_the_features_of_another_account(
    admin_client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    other = await user_factory(email="flagged@example.com", password="secret123")

    response = await admin_client.get(f"/api/v1/users/{other['id']}/features")

    assert response.status_code == 200
    body = response.json()
    assert body["features"] is None
    assert "items" in body["available"]


async def test_an_administrator_narrows_the_features_of_another_account(
    admin_client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    other = await user_factory(email="flagged@example.com", password="secret123")

    response = await admin_client.put(
        f"/api/v1/users/{other['id']}/features", json={"features": "items"}
    )

    assert response.status_code == 200
    assert response.json()["features"] == "items"

    again = await admin_client.get(f"/api/v1/users/{other['id']}/features")
    assert again.json()["features"] == "items"


async def test_an_administrator_hands_an_account_back_to_the_defaults(
    admin_client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    other = await user_factory(email="flagged@example.com", password="secret123")
    await admin_client.put(
        f"/api/v1/users/{other['id']}/features", json={"features": "items"}
    )

    response = await admin_client.put(
        f"/api/v1/users/{other['id']}/features", json={"features": None}
    )

    assert response.json()["features"] is None


async def test_changing_the_features_of_an_account_requires_the_permission(
    auth_client: AsyncClient,
) -> None:
    assert (await auth_client.get("/api/v1/users/1/features")).status_code == 403
    assert (
        await auth_client.put("/api/v1/users/1/features", json={"features": "items"})
    ).status_code == 403
