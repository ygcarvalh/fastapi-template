from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.context import audit_suppressed
from app.core.audit.listeners import UnauditedBulkMutation
from app.core.audit.policy import REDACTED_PLACEHOLDER, AuditAction
from app.core.observability.request_context import REQUEST_ID_HEADER
from app.models.audit_log import AuditLog
from app.models.item import Item
from app.models.role import Role
from app.models.user import User, UserRole

PASSWORD = "secret123"

UserFactory = Callable[..., Awaitable[dict[str, object]]]


async def _rows(session: AsyncSession, table: str) -> list[AuditLog]:
    found = await session.execute(
        select(AuditLog).where(AuditLog.table_name == table).order_by(AuditLog.id)
    )
    return list(found.scalars().all())


async def _grant_admin(session: AsyncSession, email: str) -> None:
    account = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one()
    role = (
        await session.execute(select(Role).where(Role.name == UserRole.ADMIN))
    ).scalar_one()
    account.roles = [role]
    await session.flush()


async def _links_for(
    session: AsyncSession, user_id: object, action: AuditAction
) -> list[AuditLog]:
    rows = await _rows(session, "user_roles")
    return [
        row
        for row in rows
        if row.action == action
        and row.row_pk is not None
        and row.row_pk.startswith(f"{user_id}:")
    ]


def _change(row: AuditLog, column: str) -> dict[str, Any]:
    value: dict[str, Any] = row.changes[column]
    return value


async def test_an_insert_is_recorded_with_the_key_the_database_assigned(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await auth_client.post("/api/v1/items", json={"title": "Task one"})

    rows = await _rows(db_session, "items")
    assert [row.action for row in rows] == [AuditAction.INSERT]
    assert rows[0].row_pk == str(created.json()["id"])
    assert _change(rows[0], "title") == {"old": None, "new": "Task one"}


async def test_an_update_records_only_the_columns_that_moved(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    await auth_client.patch("/api/v1/users/me", json={"name": "Ada"})

    rows = await _rows(db_session, "users")
    updates = [row for row in rows if row.action == AuditAction.UPDATE]
    assert len(updates) == 1
    assert updates[0].changes == {"name": {"old": None, "new": "Ada"}}


async def test_a_soft_delete_is_not_filed_as_an_ordinary_update(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await auth_client.post("/api/v1/items", json={"title": "doomed"})
    await auth_client.delete(f"/api/v1/items/{created.json()['id']}")

    rows = await _rows(db_session, "items")
    assert [row.action for row in rows] == [
        AuditAction.INSERT,
        AuditAction.SOFT_DELETE,
    ]


async def test_granting_a_role_is_recorded_by_name_not_only_by_key(
    client: AsyncClient, db_session: AsyncSession, user_factory: UserFactory
) -> None:
    await user_factory(email="bootstrap@example.com", password=PASSWORD)
    admin = await user_factory(email="audit-admin@example.com", password=PASSWORD)
    target = await user_factory(email="audit-target@example.com", password=PASSWORD)
    await _grant_admin(db_session, "audit-admin@example.com")
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "audit-admin@example.com", "password": PASSWORD},
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    await client.post(
        f"/api/v1/users/{target['id']}/roles", json={"role": UserRole.ADMIN}
    )

    granted = await _links_for(db_session, target["id"], AuditAction.LINK)
    assert [_change(row, "name")["new"] for row in granted] == [
        "user",
        UserRole.ADMIN,
    ]
    assert [row.actor_id for row in granted] == [None, admin["id"]]
    client.headers.pop("Authorization", None)


async def test_revoking_a_role_is_recorded_as_the_link_coming_apart(
    client: AsyncClient, db_session: AsyncSession, user_factory: UserFactory
) -> None:
    await user_factory(email="bootstrap@example.com", password=PASSWORD)
    await user_factory(email="revoke-admin@example.com", password=PASSWORD)
    target = await user_factory(email="revoke-target@example.com", password=PASSWORD)
    await _grant_admin(db_session, "revoke-admin@example.com")
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "revoke-admin@example.com", "password": PASSWORD},
    )
    client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"

    await client.delete(f"/api/v1/users/{target['id']}/roles/user")

    revoked = await _links_for(db_session, target["id"], AuditAction.UNLINK)
    assert [_change(row, "name") for row in revoked] == [{"old": "user", "new": None}]
    client.headers.pop("Authorization", None)


async def test_a_password_change_records_that_it_happened_and_nothing_more(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    response = await auth_client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "another-secret"},
    )
    assert response.status_code == 204

    rows = await _rows(db_session, "users")
    changed = [row for row in rows if row.action == AuditAction.UPDATE]
    assert len(changed) == 1
    assert _change(changed[0], "hashed_password") == {
        "old": REDACTED_PLACEHOLDER,
        "new": REDACTED_PLACEHOLDER,
    }


async def test_the_token_tables_stay_out_of_the_trail(
    client: AsyncClient, db_session: AsyncSession, user_factory: UserFactory
) -> None:
    await user_factory(email="bootstrap@example.com", password=PASSWORD)
    await user_factory(email="noise@example.com", password=PASSWORD)

    await client.post(
        "/api/v1/auth/login",
        data={"username": "noise@example.com", "password": PASSWORD},
    )

    assert await _rows(db_session, "refresh_tokens") == []


async def test_a_row_that_never_existed_leaves_no_trace(
    client: AsyncClient, db_session: AsyncSession, user_factory: UserFactory
) -> None:
    await user_factory(email="bootstrap@example.com", password=PASSWORD)
    await user_factory(email="taken@example.com", password=PASSWORD)

    rejected = await client.post(
        "/api/v1/users", json={"email": "taken@example.com", "password": PASSWORD}
    )
    assert rejected.status_code == 409

    inserts = [
        row
        for row in await _rows(db_session, "users")
        if row.action == AuditAction.INSERT
    ]
    assert len(inserts) == 2


async def test_a_row_carries_the_request_that_produced_it(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    created = await auth_client.post("/api/v1/items", json={"title": "traceable"})

    rows = await _rows(db_session, "items")
    assert rows[0].request_id == created.headers[REQUEST_ID_HEADER]
    assert rows[0].source == "request"
    assert rows[0].impersonator_id is None
    assert not rows[0].truncated


async def test_an_anonymous_mutation_is_recorded_without_an_actor(
    client: AsyncClient, db_session: AsyncSession, user_factory: UserFactory
) -> None:
    await user_factory(email="anon@example.com", password=PASSWORD)

    rows = await _rows(db_session, "users")
    assert [row.actor_id for row in rows] == [None]
    assert rows[0].method == "POST"
    assert rows[0].path == "/api/v1/users"


async def test_a_bulk_statement_that_would_go_unrecorded_is_refused(
    db_session: AsyncSession,
) -> None:
    with pytest.raises(UnauditedBulkMutation):
        await db_session.execute(delete(Item).where(Item.id == 0))


async def test_maintenance_that_says_so_is_still_allowed_through(
    db_session: AsyncSession,
) -> None:
    with audit_suppressed():
        await db_session.execute(delete(Item).where(Item.id == 0))
