from collections.abc import Awaitable, Callable

from httpx import AsyncClient

EMAIL = "refresh@example.com"
PASSWORD = "secret123"

UserFactory = Callable[..., Awaitable[dict[str, object]]]


async def _login(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", data={"username": EMAIL, "password": PASSWORD}
    )
    body: dict[str, str] = response.json()
    return body


async def test_login_returns_both_tokens(
    client: AsyncClient, user_factory: UserFactory
) -> None:
    await user_factory(email=EMAIL, password=PASSWORD)

    tokens = await _login(client)

    assert tokens["token_type"] == "bearer"
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["access_token"] != tokens["refresh_token"]


async def test_refresh_issues_a_new_pair(
    client: AsyncClient, user_factory: UserFactory
) -> None:
    await user_factory(email=EMAIL, password=PASSWORD)
    tokens = await _login(client)

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 200
    refreshed = response.json()
    assert refreshed["access_token"]
    assert refreshed["refresh_token"]


async def test_refreshed_access_token_works_on_a_protected_route(
    client: AsyncClient, user_factory: UserFactory
) -> None:
    await user_factory(email=EMAIL, password=PASSWORD)
    tokens = await _login(client)
    refreshed = (
        await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
    ).json()

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {refreshed['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == EMAIL


async def test_an_access_token_cannot_be_exchanged_for_a_new_pair(
    client: AsyncClient, user_factory: UserFactory
) -> None:
    await user_factory(email=EMAIL, password=PASSWORD)
    tokens = await _login(client)

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )

    assert response.status_code == 401


async def test_a_refresh_token_is_not_accepted_as_a_bearer_token(
    client: AsyncClient, user_factory: UserFactory
) -> None:
    await user_factory(email=EMAIL, password=PASSWORD)
    tokens = await _login(client)

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )

    assert response.status_code == 401


async def test_a_deactivated_account_cannot_refresh(
    client: AsyncClient, user_factory: UserFactory
) -> None:
    await user_factory(email=EMAIL, password=PASSWORD)
    tokens = await _login(client)
    await client.request(
        "DELETE",
        "/api/v1/users/me",
        json={"password": PASSWORD},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 401
