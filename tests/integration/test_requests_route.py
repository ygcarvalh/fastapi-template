from collections.abc import AsyncGenerator, Awaitable, Callable

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.request_log import RequestLog
from app.models.role import Role
from app.models.user import User, UserRole

Rows = Callable[..., Awaitable[RequestLog]]


@pytest_asyncio.fixture
async def add_row(db_session: AsyncSession) -> AsyncGenerator[Rows]:
    async def _add(
        request_id: str,
        *,
        status_code: int = 200,
        user_id: int | None = None,
        path: str = "/api/v1/items",
    ) -> RequestLog:
        entry = RequestLog(
            request_id=request_id,
            method="GET",
            path=path,
            status_code=status_code,
            duration_ms=1.0,
            client_ip="127.0.0.1",
            user_id=user_id,
        )
        db_session.add(entry)
        await db_session.flush()
        return entry

    yield _add


async def _current_user_id(db_session: AsyncSession, email: str) -> int:
    user = (
        (await db_session.execute(select(User).where(User.email == email)))
        .scalars()
        .one()
    )
    return user.id


async def test_a_user_sees_only_their_own_rows(
    auth_client: AsyncClient, db_session: AsyncSession, add_row: Rows
) -> None:
    owner_id = await _current_user_id(db_session, "auth@example.com")
    await add_row("mine", user_id=owner_id)
    await add_row("someone-else", user_id=owner_id + 1000)
    await add_row("anonymous")

    response = await auth_client.get("/api/v1/requests")

    assert response.status_code == 200
    body = response.json()
    assert [item["request_id"] for item in body["items"]] == ["mine"]
    assert body["items"][0]["outcome"] == "success"
    assert body["next_cursor"] is None


async def test_an_admin_sees_every_row(
    auth_client: AsyncClient, db_session: AsyncSession, add_row: Rows
) -> None:
    user = (
        (await db_session.execute(select(User).where(User.email == "auth@example.com")))
        .scalars()
        .one()
    )
    user.roles = [
        (
            await db_session.execute(select(Role).where(Role.name == UserRole.ADMIN))
        ).scalar_one()
    ]
    await db_session.flush()
    await add_row("mine", user_id=user.id)
    await add_row("anonymous")

    response = await auth_client.get("/api/v1/requests")

    assert {item["request_id"] for item in response.json()["items"]} == {
        "mine",
        "anonymous",
    }


async def test_the_outcome_filter_selects_the_class(
    auth_client: AsyncClient, db_session: AsyncSession, add_row: Rows
) -> None:
    owner_id = await _current_user_id(db_session, "auth@example.com")
    await add_row("fine", user_id=owner_id)
    await add_row("refused", status_code=409, user_id=owner_id)
    await add_row("crashed", status_code=500, user_id=owner_id)

    warnings = await auth_client.get("/api/v1/requests", params={"outcome": "warning"})
    errors = await auth_client.get("/api/v1/requests", params={"outcome": "error"})

    assert [item["request_id"] for item in warnings.json()["items"]] == ["refused"]
    assert [item["request_id"] for item in errors.json()["items"]] == ["crashed"]


async def test_the_path_filter_matches_a_fragment(
    auth_client: AsyncClient, db_session: AsyncSession, add_row: Rows
) -> None:
    owner_id = await _current_user_id(db_session, "auth@example.com")
    await add_row("items", user_id=owner_id, path="/api/v1/items")
    await add_row("users", user_id=owner_id, path="/api/v1/users/me")

    response = await auth_client.get(
        "/api/v1/requests", params={"path": "/api/v1/users"}
    )

    assert [item["request_id"] for item in response.json()["items"]] == ["users"]


async def test_a_cursor_walks_the_pages_without_repeating_a_row(
    auth_client: AsyncClient, db_session: AsyncSession, add_row: Rows
) -> None:
    owner_id = await _current_user_id(db_session, "auth@example.com")
    for index in range(3):
        await add_row(f"row-{index}", user_id=owner_id)

    first = (await auth_client.get("/api/v1/requests", params={"limit": 2})).json()
    second = (
        await auth_client.get(
            "/api/v1/requests",
            params={"limit": 2, "cursor": first["next_cursor"]},
        )
    ).json()

    assert first["limit"] == 2
    assert len(first["items"]) == 2
    assert first["next_cursor"]
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None
    seen = [item["request_id"] for item in first["items"] + second["items"]]
    assert len(seen) == len(set(seen)) == 3


async def test_a_cursor_the_api_did_not_issue_is_refused(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get(
        "/api/v1/requests", params={"cursor": "bm90LWEtY3Vyc29y"}
    )

    assert response.status_code == 422


async def test_one_row_is_readable_by_its_correlation_id(
    auth_client: AsyncClient, db_session: AsyncSession, add_row: Rows
) -> None:
    owner_id = await _current_user_id(db_session, "auth@example.com")
    await add_row("wanted", user_id=owner_id)

    response = await auth_client.get("/api/v1/requests/wanted")

    assert response.status_code == 200
    assert response.json()["request_id"] == "wanted"


async def test_an_unknown_correlation_id_is_a_404(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/requests/nothing-here")

    assert response.status_code == 404
    assert response.json()["message"] == "Request not found"


async def test_the_list_needs_a_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/requests")

    assert response.status_code == 401
