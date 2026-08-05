from collections.abc import AsyncGenerator, Awaitable, Callable

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    stored.scalar_one().role = UserRole.ADMIN
    await db_session.flush()

    login = await client.post(
        "/api/v1/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    token = login.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
    client.headers.pop("Authorization", None)


async def test_new_users_are_not_administrators(client: AsyncClient) -> None:
    created = await client.post(
        "/api/v1/users", json={"email": "plain@example.com", "password": "secret123"}
    )

    assert created.json()["role"] == "user"


async def test_listing_users_requires_the_admin_role(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/users")

    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


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
