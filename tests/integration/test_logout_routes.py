from collections.abc import Awaitable, Callable

from httpx import AsyncClient

EMAIL = "logout@example.com"
PASSWORD = "secret123"

UserFactory = Callable[..., Awaitable[dict[str, object]]]


async def _login(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login", data={"username": EMAIL, "password": PASSWORD}
    )
    tokens: dict[str, str] = response.json()
    return tokens


async def test_signing_out_retires_the_refresh_token(
    client: AsyncClient, user_factory: UserFactory
) -> None:
    await user_factory(email=EMAIL, password=PASSWORD)
    tokens = await _login(client)

    signed_out = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    refused = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert signed_out.status_code == 204
    assert refused.status_code == 401


async def test_signing_out_twice_is_harmless(
    client: AsyncClient, user_factory: UserFactory
) -> None:
    await user_factory(email=EMAIL, password=PASSWORD)
    tokens = await _login(client)

    first = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )
    second = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
    )

    assert (first.status_code, second.status_code) == (204, 204)


async def test_an_unknown_token_is_accepted_without_saying_so(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": "not-a-token-we-issued"}
    )

    assert response.status_code == 204


async def test_a_refresh_token_nobody_stored_is_refused(
    client: AsyncClient, user_factory: UserFactory
) -> None:
    await user_factory(email=EMAIL, password=PASSWORD)
    tokens = await _login(client)
    forged = f"{tokens['refresh_token'][:-2]}xx"

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": forged})

    assert response.status_code == 401


async def test_changing_the_password_closes_every_other_session(
    client: AsyncClient, user_factory: UserFactory
) -> None:
    await user_factory(email=EMAIL, password=PASSWORD)
    first = await _login(client)
    second = await _login(client)

    changed = await client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "a-brand-new-secret"},
        headers={"Authorization": f"Bearer {first['access_token']}"},
    )

    assert changed.status_code == 204
    for tokens in (first, second):
        refused = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert refused.status_code == 401
