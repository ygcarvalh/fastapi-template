from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

EMAIL = "stale@example.com"
PASSWORD = "the-first-password"
NEW_PASSWORD = "the-second-password"


async def _signed_in(client: AsyncClient) -> dict[str, str]:
    login = await client.post(
        "/api/v1/auth/login", data={"username": EMAIL, "password": PASSWORD}
    )
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def test_a_token_older_than_the_password_is_refused(
    client: AsyncClient,
    db_session: AsyncSession,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    await user_factory(email=EMAIL, password=PASSWORD)
    headers = await _signed_in(client)
    assert (await client.get("/api/v1/users/me", headers=headers)).status_code == 200

    user = (
        await db_session.execute(select(User).where(User.email == EMAIL))
    ).scalar_one()
    user.password_changed_at = datetime.now(UTC) + timedelta(seconds=5)
    await db_session.commit()

    refused = await client.get("/api/v1/users/me", headers=headers)

    assert refused.status_code == 401
    assert refused.json()["code"] == "auth.invalidCredentials"


async def test_a_token_minted_after_the_change_keeps_working(
    client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    await user_factory(email=EMAIL, password=PASSWORD)
    changed = await client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=await _signed_in(client),
    )
    assert changed.status_code == 204

    second = await client.post(
        "/api/v1/auth/login", data={"username": EMAIL, "password": NEW_PASSWORD}
    )

    me = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {second.json()['access_token']}"},
    )
    assert me.status_code == 200


async def test_an_account_that_never_changed_its_password_is_untouched(
    client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    await user_factory(email=EMAIL, password=PASSWORD)

    me = await client.get("/api/v1/users/me", headers=await _signed_in(client))

    assert me.status_code == 200
