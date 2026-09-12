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
    stored.scalar_one().roles = [admin_role]
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
    await admin_client.post(
        f"/api/v1/users/{holder['id']}/roles", json={"role": "finance"}
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


async def test_an_account_joins_a_role_that_was_just_created(
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

    response = await admin_client.post(
        f"/api/v1/users/{other['id']}/roles", json={"role": "finance"}
    )

    assert response.status_code == 200
    assert response.json()["roles"] == ["finance", "user"]


async def test_the_members_of_a_role_are_listed(
    admin_client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    created = (
        await admin_client.post("/api/v1/roles", json={"name": "finance", "grants": []})
    ).json()
    holder = await user_factory(email="member@example.com", password=PASSWORD)
    await admin_client.post(
        f"/api/v1/roles/{created['id']}/users", json={"user_id": holder["id"]}
    )

    response = await admin_client.get(f"/api/v1/roles/{created['id']}/users")

    assert response.status_code == 200
    assert [row["email"] for row in response.json()] == ["member@example.com"]


async def test_a_member_added_from_the_role_shows_up_on_the_account(
    admin_client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    created = (
        await admin_client.post("/api/v1/roles", json={"name": "finance", "grants": []})
    ).json()
    holder = await user_factory(email="joined@example.com", password=PASSWORD)

    await admin_client.post(
        f"/api/v1/roles/{created['id']}/users", json={"user_id": holder["id"]}
    )

    account = await admin_client.get(f"/api/v1/users/{holder['id']}")
    assert account.json()["roles"] == ["finance", "user"]


async def test_a_member_is_taken_off_a_role(
    admin_client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    created = (
        await admin_client.post("/api/v1/roles", json={"name": "finance", "grants": []})
    ).json()
    holder = await user_factory(email="leaving@example.com", password=PASSWORD)
    await admin_client.post(
        f"/api/v1/roles/{created['id']}/users", json={"user_id": holder["id"]}
    )

    response = await admin_client.delete(
        f"/api/v1/roles/{created['id']}/users/{holder['id']}"
    )

    assert response.status_code == 200
    assert response.json()["roles"] == ["user"]
    assert (await admin_client.get(f"/api/v1/roles/{created['id']}/users")).json() == []


async def test_an_administrator_cannot_leave_the_superadmin_role_from_its_own_screen(
    admin_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    stored = await db_session.execute(select(User).where(User.email == ADMIN_EMAIL))
    admin_id = stored.scalar_one().id
    roles = (await admin_client.get("/api/v1/roles")).json()
    role_id = next(role["id"] for role in roles if role["name"] == "superadmin")

    response = await admin_client.delete(f"/api/v1/roles/{role_id}/users/{admin_id}")

    assert response.status_code == 403


async def test_the_members_of_a_missing_role_are_a_404(
    admin_client: AsyncClient,
) -> None:
    assert (await admin_client.get("/api/v1/roles/404/users")).status_code == 404


async def test_a_role_carries_a_feature_list_of_its_own(
    admin_client: AsyncClient,
) -> None:
    created = (
        await admin_client.post(
            "/api/v1/roles",
            json={"name": "finance", "grants": [], "features": "items"},
        )
    ).json()

    assert created["features"] == "items"

    updated = await admin_client.put(
        f"/api/v1/roles/{created['id']}",
        json={"name": "finance", "grants": [], "features": None},
    )

    assert updated.json()["features"] is None


async def test_an_account_inherits_the_features_of_its_roles(
    admin_client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    await admin_client.post(
        "/api/v1/roles",
        json={"name": "finance", "grants": [], "features": "items"},
    )
    holder = await user_factory(email="heir@example.com", password=PASSWORD)
    await admin_client.post(
        f"/api/v1/users/{holder['id']}/roles", json={"role": "finance"}
    )

    login = await admin_client.post(
        "/api/v1/auth/login",
        data={"username": "heir@example.com", "password": PASSWORD},
    )
    admin_client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    response = await admin_client.get("/api/v1/features")

    assert response.json()["inherited"] == ["items"]


async def test_an_account_whose_roles_say_nothing_inherits_nothing(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.get("/api/v1/features")

    assert response.json()["inherited"] is None


async def test_managing_the_members_of_a_role_requires_the_permission(
    auth_client: AsyncClient,
) -> None:
    assert (await auth_client.get("/api/v1/roles/1/users")).status_code == 403
    assert (
        await auth_client.post("/api/v1/roles/1/users", json={"user_id": 1})
    ).status_code == 403
    assert (await auth_client.delete("/api/v1/roles/1/users/1")).status_code == 403


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
