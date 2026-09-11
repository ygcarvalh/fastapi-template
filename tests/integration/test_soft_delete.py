from collections.abc import Awaitable, Callable

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.user import User

RETIRED_EMAIL = "retired@example.com"
PASSWORD = "secret123"


async def _login(client: AsyncClient, email: str, password: str) -> int:
    response = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": password}
    )
    return response.status_code


async def test_deleting_an_item_keeps_the_row_and_stamps_it(
    auth_client: AsyncClient, db_session: AsyncSession
) -> None:
    item_id = (
        await auth_client.post("/api/v1/items", json={"title": "retire me"})
    ).json()["id"]

    assert (await auth_client.delete(f"/api/v1/items/{item_id}")).status_code == 204

    stored = await db_session.execute(select(Item).where(Item.id == item_id))
    item = stored.scalar_one()
    assert item.deleted_at is not None


async def test_deleted_items_disappear_from_listings(
    auth_client: AsyncClient,
) -> None:
    item_id = (await auth_client.post("/api/v1/items", json={"title": "gone"})).json()[
        "id"
    ]
    await auth_client.delete(f"/api/v1/items/{item_id}")

    body = (await auth_client.get("/api/v1/items")).json()

    assert body["total"] == 0
    assert body["items"] == []


async def test_deactivating_an_account_invalidates_its_token(
    client: AsyncClient, user_factory: Callable[..., Awaitable[dict[str, object]]]
) -> None:
    await user_factory(email=RETIRED_EMAIL, password=PASSWORD)
    login = await client.post(
        "/api/v1/auth/login", data={"username": RETIRED_EMAIL, "password": PASSWORD}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    response = await client.request(
        "DELETE", "/api/v1/users/me", json={"password": PASSWORD}, headers=headers
    )
    assert response.status_code == 204
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 401


async def test_deactivating_with_the_wrong_password_is_refused(
    client: AsyncClient, user_factory: Callable[..., Awaitable[dict[str, object]]]
) -> None:
    await user_factory(email=RETIRED_EMAIL, password=PASSWORD)
    login = await client.post(
        "/api/v1/auth/login", data={"username": RETIRED_EMAIL, "password": PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.request(
        "DELETE",
        "/api/v1/users/me",
        json={"password": "wrong-password"},
        headers=headers,
    )

    assert response.status_code == 403
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 200


async def test_deactivated_accounts_cannot_log_in(
    client: AsyncClient, user_factory: Callable[..., Awaitable[dict[str, object]]]
) -> None:
    await user_factory(email=RETIRED_EMAIL, password=PASSWORD)
    login = await client.post(
        "/api/v1/auth/login", data={"username": RETIRED_EMAIL, "password": PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    await client.request(
        "DELETE", "/api/v1/users/me", json={"password": PASSWORD}, headers=headers
    )

    assert await _login(client, RETIRED_EMAIL, PASSWORD) == 401


async def test_a_deactivated_address_can_register_again(
    client: AsyncClient, user_factory: Callable[..., Awaitable[dict[str, object]]]
) -> None:
    await user_factory(email=RETIRED_EMAIL, password=PASSWORD)
    login = await client.post(
        "/api/v1/auth/login", data={"username": RETIRED_EMAIL, "password": PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    await client.request(
        "DELETE", "/api/v1/users/me", json={"password": PASSWORD}, headers=headers
    )

    again = await client.post(
        "/api/v1/users", json={"email": RETIRED_EMAIL, "password": PASSWORD}
    )

    assert again.status_code == 201


async def test_deactivating_an_account_also_retires_its_items(
    client: AsyncClient,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    await user_factory(email=RETIRED_EMAIL, password=PASSWORD)
    login = await client.post(
        "/api/v1/auth/login", data={"username": RETIRED_EMAIL, "password": PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    created = await client.post(
        "/api/v1/items", json={"title": "owned"}, headers=headers
    )
    item_id = created.json()["id"]

    await client.request(
        "DELETE", "/api/v1/users/me", json={"password": PASSWORD}, headers=headers
    )

    stored = await db_session.execute(select(Item).where(Item.id == item_id))
    assert stored.scalar_one().deleted_at is not None


async def test_the_user_row_survives_deactivation(
    client: AsyncClient,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    await user_factory(email=RETIRED_EMAIL, password=PASSWORD)
    login = await client.post(
        "/api/v1/auth/login", data={"username": RETIRED_EMAIL, "password": PASSWORD}
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    await client.request(
        "DELETE", "/api/v1/users/me", json={"password": PASSWORD}, headers=headers
    )

    stored = await db_session.execute(
        select(User).where(User.email == RETIRED_EMAIL).order_by(User.id)
    )
    rows = stored.scalars().all()
    assert len(rows) == 1
    assert rows[0].deleted_at is not None
