from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.context import audit_suppressed
from app.core.audit.policy import AuditAction
from app.core.config import get_settings
from app.db.session import get_session
from app.main import create_app
from app.models.audit_log import AuditLog
from app.models.role import Role
from app.models.user import User, UserRole
from app.schemas.pagination import encode_cursor

ADMIN_EMAIL = "audit-reader@example.com"
PASSWORD = "secret123"
AUDIT_URL = "/api/v1/audit"
ONLY_ITEMS = {"table_name": "items"}

UserFactory = Callable[..., Awaitable[dict[str, object]]]


@pytest_asyncio.fixture
async def admin_client(
    client: AsyncClient,
    db_session: AsyncSession,
    user_factory: UserFactory,
) -> AsyncGenerator[AsyncClient]:
    await user_factory(email=ADMIN_EMAIL, password=PASSWORD)
    account = (
        await db_session.execute(select(User).where(User.email == ADMIN_EMAIL))
    ).scalar_one()
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


@pytest_asyncio.fixture
async def rows(db_session: AsyncSession) -> Callable[..., Awaitable[AuditLog]]:
    async def _add(
        *,
        actor_id: int | None = None,
        table_name: str = "items",
        action: AuditAction = AuditAction.INSERT,
        request_id: str = "abc",
        minutes: int = 0,
    ) -> AuditLog:
        entry = AuditLog(
            occurred_at=datetime(2026, 9, 12, 12, tzinfo=UTC)
            + timedelta(minutes=minutes),
            request_id=request_id,
            actor_id=actor_id,
            source="request",
            table_name=table_name,
            action=action,
            row_pk="1",
            changes={"title": {"old": None, "new": "one"}},
        )
        with audit_suppressed():
            db_session.add(entry)
            await db_session.flush()
        return entry

    return _add


async def test_the_trail_needs_a_token(client: AsyncClient) -> None:
    assert (await client.get(AUDIT_URL)).status_code == 401


async def test_an_account_without_the_permission_is_refused(
    auth_client: AsyncClient,
) -> None:
    assert (await auth_client.get(AUDIT_URL)).status_code == 403


async def test_a_page_carries_the_envelope_the_frontend_reads(
    admin_client: AsyncClient, rows: Callable[..., Awaitable[AuditLog]]
) -> None:
    await rows(minutes=1)

    body = (await admin_client.get(AUDIT_URL, params=ONLY_ITEMS)).json()

    assert body["limit"] == 20
    assert body["items"][0]["table_name"] == "items"
    assert body["items"][0]["changes"] == {"title": {"old": None, "new": "one"}}


async def test_a_full_page_hands_back_a_cursor_that_reads_the_next_one(
    admin_client: AsyncClient, rows: Callable[..., Awaitable[AuditLog]]
) -> None:
    for minute in range(3):
        await rows(minutes=minute)

    first = (
        await admin_client.get(AUDIT_URL, params={**ONLY_ITEMS, "limit": 2})
    ).json()
    assert len(first["items"]) == 2
    assert first["next_cursor"] is not None

    second = (
        await admin_client.get(
            AUDIT_URL,
            params={**ONLY_ITEMS, "limit": 2, "cursor": first["next_cursor"]},
        )
    ).json()

    assert len(second["items"]) == 1
    assert second["next_cursor"] is None


async def test_each_filter_narrows_the_page(
    admin_client: AsyncClient, rows: Callable[..., Awaitable[AuditLog]]
) -> None:
    await rows(table_name="items", action=AuditAction.INSERT, request_id="first")
    await rows(
        table_name="roles", action=AuditAction.UPDATE, request_id="second", minutes=1
    )

    by_table = await admin_client.get(AUDIT_URL, params={"table_name": "roles"})
    by_action = await admin_client.get(
        AUDIT_URL, params={**ONLY_ITEMS, "action": "insert"}
    )
    by_request = await admin_client.get(AUDIT_URL, params={"request_id": "first"})

    assert [row["table_name"] for row in by_table.json()["items"]] == ["roles"]
    assert [row["request_id"] for row in by_action.json()["items"]] == ["first"]
    assert [row["request_id"] for row in by_request.json()["items"]] == ["first"]


async def test_a_window_narrows_the_page_at_both_ends(
    admin_client: AsyncClient, rows: Callable[..., Awaitable[AuditLog]]
) -> None:
    await rows(request_id="early", minutes=0)
    await rows(request_id="late", minutes=10)

    response = await admin_client.get(
        AUDIT_URL,
        params={
            **ONLY_ITEMS,
            "since": "2026-09-12T12:05:00Z",
            "until": "2026-09-12T13:00:00Z",
        },
    )

    assert [row["request_id"] for row in response.json()["items"]] == ["late"]


async def test_a_window_that_ends_before_it_starts_is_refused(
    admin_client: AsyncClient,
) -> None:
    response = await admin_client.get(
        AUDIT_URL,
        params={"since": "2026-09-12T12:00:00Z", "until": "2026-09-11T12:00:00Z"},
    )

    assert response.status_code == 422


async def test_a_cursor_this_api_never_issued_is_refused(
    admin_client: AsyncClient,
) -> None:
    assert (
        await admin_client.get(AUDIT_URL, params={"cursor": "notacursor"})
    ).status_code == 422


async def test_an_action_the_trail_never_records_is_refused(
    admin_client: AsyncClient,
) -> None:
    assert (
        await admin_client.get(AUDIT_URL, params={"action": "sideways"})
    ).status_code == 422


async def test_one_entry_reads_back_by_its_key(
    admin_client: AsyncClient, rows: Callable[..., Awaitable[AuditLog]]
) -> None:
    entry = await rows()

    response = await admin_client.get(f"{AUDIT_URL}/{entry.id}")

    assert response.status_code == 200
    assert response.json()["id"] == entry.id


async def test_an_entry_that_never_existed_is_not_found(
    admin_client: AsyncClient,
) -> None:
    assert (await admin_client.get(f"{AUDIT_URL}/999999")).status_code == 404


async def test_a_cursor_reads_from_where_the_reader_left_off(
    admin_client: AsyncClient, rows: Callable[..., Awaitable[AuditLog]]
) -> None:
    oldest = await rows(minutes=0)
    await rows(minutes=1)

    body = (
        await admin_client.get(
            AUDIT_URL,
            params={
                **ONLY_ITEMS,
                "cursor": encode_cursor(oldest.occurred_at, oldest.id + 1),
            },
        )
    ).json()

    assert [row["id"] for row in body["items"]] == [oldest.id]


@pytest_asyncio.fixture
async def without_the_feature(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncGenerator[AsyncClient]:
    get_settings.cache_clear()
    monkeypatch.setenv("FEATURE_FLAGS", "items")
    app = create_app()

    async def override_get_session() -> AsyncGenerator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
    get_settings.cache_clear()


async def test_a_deployment_that_withholds_the_trail_answers_404(
    without_the_feature: AsyncClient,
) -> None:
    assert (await without_the_feature.get(AUDIT_URL)).status_code == 404
