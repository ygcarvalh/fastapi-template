from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any, NamedTuple

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.policy import AuditAction
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User, UserRole

ADMIN_EMAIL = "impersonator@example.com"
TARGET_EMAIL = "impersonated@example.com"
PASSWORD = "secret123"

UserFactory = Callable[..., Awaitable[dict[str, Any]]]


class Cast(NamedTuple):
    admin_id: int
    target_id: int


async def _role(session: AsyncSession, name: str) -> Role:
    return (await session.execute(select(Role).where(Role.name == name))).scalar_one()


async def _account(session: AsyncSession, email: str) -> User:
    return (await session.execute(select(User).where(User.email == email))).scalar_one()


async def _sign_in(client: AsyncClient, email: str) -> str:
    login = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": PASSWORD}
    )
    token: str = login.json()["access_token"]
    return token


@pytest_asyncio.fixture
async def cast(
    client: AsyncClient,
    db_session: AsyncSession,
    user_factory: UserFactory,
) -> AsyncGenerator[Cast]:
    await user_factory(email="bootstrap@example.com", password=PASSWORD)
    admin = await user_factory(email=ADMIN_EMAIL, password=PASSWORD)
    target = await user_factory(email=TARGET_EMAIL, password=PASSWORD)
    account = await _account(db_session, ADMIN_EMAIL)
    account.roles = [await _role(db_session, UserRole.ADMIN)]
    await db_session.flush()

    client.headers["Authorization"] = f"Bearer {await _sign_in(client, ADMIN_EMAIL)}"
    yield Cast(admin_id=admin["id"], target_id=target["id"])
    client.headers.pop("Authorization", None)


async def _become(client: AsyncClient, user_id: int) -> dict[str, Any]:
    response = await client.post(f"/api/v1/auth/impersonate/{user_id}")
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    client.headers["Authorization"] = f"Bearer {body['access_token']}"
    return body


async def _audit(session: AsyncSession, table: str) -> list[AuditLog]:
    found = await session.execute(
        select(AuditLog).where(AuditLog.table_name == table).order_by(AuditLog.id)
    )
    return list(found.scalars().all())


async def test_the_grant_names_both_accounts_and_carries_no_refresh_token(
    client: AsyncClient, cast: Cast
) -> None:
    body = await _become(client, cast.target_id)

    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert "refresh_token" not in body
    assert body["user"]["email"] == TARGET_EMAIL
    assert body["impersonator"]["email"] == ADMIN_EMAIL


async def test_the_token_reads_the_system_as_the_other_account(
    client: AsyncClient, cast: Cast
) -> None:
    await _become(client, cast.target_id)

    me = await client.get("/api/v1/users/me")

    assert me.json()["email"] == TARGET_EMAIL


async def test_the_borrowed_session_loses_what_the_other_account_never_had(
    client: AsyncClient, cast: Cast
) -> None:
    await _become(client, cast.target_id)

    assert (await client.get("/api/v1/users")).status_code == 403


async def test_the_borrowed_session_still_writes_what_that_account_may_write(
    client: AsyncClient, cast: Cast
) -> None:
    await _become(client, cast.target_id)

    created = await client.post("/api/v1/items", json={"title": "seen as them"})

    assert created.status_code == 201


async def test_permissions_cannot_be_rewritten_from_a_borrowed_session(
    client: AsyncClient, cast: Cast
) -> None:
    admin_id = cast.admin_id
    await _become(client, cast.target_id)

    assert (
        await client.post("/api/v1/roles", json={"name": "invented", "grants": []})
    ).status_code == 403
    assert (
        await client.post(f"/api/v1/users/{admin_id}/roles", json={"role": "user"})
    ).status_code == 403
    assert (
        await client.put(
            f"/api/v1/users/{admin_id}/features", json={"features": "items"}
        )
    ).status_code == 403


async def test_credentials_and_the_profile_are_out_of_reach_too(
    client: AsyncClient, cast: Cast
) -> None:
    await _become(client, cast.target_id)

    assert (
        await client.patch("/api/v1/users/me", json={"name": "renamed"})
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/auth/password",
            json={"current_password": PASSWORD, "new_password": "another-secret"},
        )
    ).status_code == 403
    assert (
        await client.request("DELETE", "/api/v1/users/me", json={"password": PASSWORD})
    ).status_code == 403


async def test_preferences_are_still_the_other_accounts_to_change(
    client: AsyncClient, cast: Cast
) -> None:
    await _become(client, cast.target_id)

    response = await client.patch(
        "/api/v1/users/me/preferences", json={"theme": "dark"}
    )

    assert response.status_code == 200


async def test_impersonation_cannot_be_chained(client: AsyncClient, cast: Cast) -> None:
    await _become(client, cast.target_id)

    again = await client.post(f"/api/v1/auth/impersonate/{cast.admin_id}")

    assert again.status_code == 403


async def test_an_account_cannot_impersonate_itself(
    client: AsyncClient, cast: Cast
) -> None:
    response = await client.post(f"/api/v1/auth/impersonate/{cast.admin_id}")

    assert response.status_code == 403


async def test_an_account_that_does_not_exist_is_not_found(
    client: AsyncClient, cast: Cast
) -> None:
    assert (await client.post("/api/v1/auth/impersonate/999999")).status_code == 404


async def test_an_account_without_the_permission_is_refused(
    auth_client: AsyncClient,
) -> None:
    assert (await auth_client.post("/api/v1/auth/impersonate/1")).status_code == 403


async def test_a_permission_taken_away_lands_before_the_token_expires(
    client: AsyncClient, db_session: AsyncSession, cast: Cast
) -> None:
    await _become(client, cast.target_id)
    assert (await client.get("/api/v1/users/me")).status_code == 200

    admin = await _account(db_session, ADMIN_EMAIL)
    admin.roles = []
    await db_session.flush()

    assert (await client.get("/api/v1/users/me")).status_code == 403


async def test_the_grant_cannot_be_replayed_as_a_refresh_token(
    client: AsyncClient, cast: Cast
) -> None:
    body = await _become(client, cast.target_id)

    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": body["access_token"]}
    )

    assert refreshed.status_code == 401


async def test_starting_and_stopping_both_reach_the_trail(
    client: AsyncClient, db_session: AsyncSession, cast: Cast
) -> None:
    await _become(client, cast.target_id)

    stopped = await client.post("/api/v1/auth/impersonate/stop")
    assert stopped.status_code == 204

    recorded = await _audit(db_session, "impersonation")
    assert [entry.action for entry in recorded] == [
        AuditAction.IMPERSONATE_START,
        AuditAction.IMPERSONATE_STOP,
    ]
    assert recorded[0].actor_id == cast.admin_id
    assert recorded[0].impersonator_id is None
    assert recorded[1].actor_id == cast.target_id
    assert recorded[1].impersonator_id == cast.admin_id


async def test_a_write_made_while_impersonating_names_both_accounts(
    client: AsyncClient, db_session: AsyncSession, cast: Cast
) -> None:
    await _become(client, cast.target_id)

    await client.post("/api/v1/items", json={"title": "in their name"})

    recorded = await _audit(db_session, "items")
    assert [entry.actor_id for entry in recorded] == [cast.target_id]
    assert [entry.impersonator_id for entry in recorded] == [cast.admin_id]


async def test_stopping_without_having_started_changes_nothing(
    client: AsyncClient, db_session: AsyncSession, cast: Cast
) -> None:
    stopped = await client.post("/api/v1/auth/impersonate/stop")

    assert stopped.status_code == 204
    assert await _audit(db_session, "impersonation") == []


async def test_accounts_cannot_be_closed_from_a_borrowed_session(
    client: AsyncClient, cast: Cast
) -> None:
    await _become(client, cast.target_id)

    assert (await client.delete(f"/api/v1/users/{cast.admin_id}")).status_code == 403
