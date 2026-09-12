from collections.abc import AsyncGenerator, Awaitable, Callable

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Role
from app.models.user import User, UserRole

ADMIN_EMAIL = "roles-admin@example.com"
PASSWORD = "secret123"


@pytest_asyncio.fixture
async def admin_client(
    client: AsyncClient,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> AsyncGenerator[AsyncClient]:
    await user_factory(email=ADMIN_EMAIL, password=PASSWORD)
    stored = await db_session.execute(select(User).where(User.email == ADMIN_EMAIL))
    admin_role = (
        await db_session.execute(select(Role).where(Role.name == UserRole.ADMIN))
    ).scalar_one()
    stored.scalar_one().role = admin_role
    await db_session.flush()

    login = await client.post(
        "/api/v1/auth/login", data={"username": ADMIN_EMAIL, "password": PASSWORD}
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
    yield client
    client.headers.pop("Authorization", None)


async def test_the_catalog_lists_every_permission(admin_client: AsyncClient) -> None:
    response = await admin_client.get("/api/v1/permissions")

    assert response.status_code == 200
    pairs = {(row["resource"], row["action"]) for row in response.json()}
    assert ("users", "read") in pairs
    assert ("roles", "create") in pairs


async def test_a_role_is_created_with_the_grants_it_was_given(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.post(
        "/api/v1/roles",
        json={
            "name": "finance",
            "grants": [{"resource": "items", "action": "read", "scope": "all"}],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "finance"
    assert body["grants"] == [
        {"resource": "items", "action": "read", "scope": "all"},
    ]


async def test_a_role_name_cannot_repeat(admin_client: AsyncClient) -> None:
    response = await admin_client.post(
        "/api/v1/roles", json={"name": "superadmin", "grants": []}
    )

    assert response.status_code == 409


async def test_a_role_is_edited_in_place(admin_client: AsyncClient) -> None:
    created = (
        await admin_client.post("/api/v1/roles", json={"name": "finance", "grants": []})
    ).json()

    response = await admin_client.put(
        f"/api/v1/roles/{created['id']}",
        json={
            "name": "finance-team",
            "grants": [{"resource": "users", "action": "read", "scope": "all"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "finance-team"
    assert response.json()["grants"] == [
        {"resource": "users", "action": "read", "scope": "all"}
    ]


async def test_an_unused_role_is_deleted(admin_client: AsyncClient) -> None:
    created = (
        await admin_client.post("/api/v1/roles", json={"name": "finance", "grants": []})
    ).json()

    assert (
        await admin_client.delete(f"/api/v1/roles/{created['id']}")
    ).status_code == 204
    assert (await admin_client.get(f"/api/v1/roles/{created['id']}")).status_code == 404


async def test_a_role_the_deployment_ships_is_kept(admin_client: AsyncClient) -> None:
    roles = (await admin_client.get("/api/v1/roles")).json()
    admin_id = next(role["id"] for role in roles if role["name"] == "superadmin")

    assert (await admin_client.delete(f"/api/v1/roles/{admin_id}")).status_code == 403


async def test_a_role_with_accounts_is_kept(
    admin_client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    created = (
        await admin_client.post("/api/v1/roles", json={"name": "finance", "grants": []})
    ).json()
    holder = await user_factory(email="holder@example.com", password=PASSWORD)
    await admin_client.patch(
        f"/api/v1/users/{holder['id']}/role", json={"role": "finance"}
    )

    assert (
        await admin_client.delete(f"/api/v1/roles/{created['id']}")
    ).status_code == 409


async def test_managing_roles_requires_the_permission(
    auth_client: AsyncClient,
) -> None:
    assert (await auth_client.get("/api/v1/roles")).status_code == 403
    assert (
        await auth_client.post("/api/v1/roles", json={"name": "x", "grants": []})
    ).status_code == 403
    assert (await auth_client.get("/api/v1/permissions")).status_code == 403


async def test_an_account_is_moved_to_a_role_that_was_just_created(
    admin_client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    await admin_client.post(
        "/api/v1/roles",
        json={
            "name": "finance",
            "grants": [{"resource": "items", "action": "read", "scope": "all"}],
        },
    )
    other = await user_factory(email="moved@example.com", password=PASSWORD)

    response = await admin_client.patch(
        f"/api/v1/users/{other['id']}/role", json={"role": "finance"}
    )

    assert response.status_code == 200
    assert response.json()["role"] == "finance"


async def test_the_administrator_role_cannot_be_narrowed(
    admin_client: AsyncClient,
) -> None:
    roles = (await admin_client.get("/api/v1/roles")).json()
    admin_id = next(role["id"] for role in roles if role["name"] == "superadmin")

    response = await admin_client.put(
        f"/api/v1/roles/{admin_id}", json={"name": "superadmin", "grants": []}
    )

    assert response.status_code == 403


async def test_an_administrator_reads_the_whole_catalog_as_its_own_permissions(
    admin_client: AsyncClient,
) -> None:
    catalog = (await admin_client.get("/api/v1/permissions")).json()

    held = (await admin_client.get("/api/v1/users/me/permissions")).json()

    assert {(row["resource"], row["action"]) for row in held} == {
        (row["resource"], row["action"]) for row in catalog
    }
    assert {row["scope"] for row in held} == {"all"}
