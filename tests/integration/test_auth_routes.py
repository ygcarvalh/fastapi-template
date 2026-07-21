from collections.abc import Awaitable, Callable

from httpx import AsyncClient


async def test_login_returns_token(
    client: AsyncClient, user_factory: Callable[..., Awaitable[dict[str, object]]]
) -> None:
    await user_factory(email="login@example.com", password="secret123")
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "login@example.com", "password": "secret123"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


async def test_login_wrong_password_returns_401(
    client: AsyncClient, user_factory: Callable[..., Awaitable[dict[str, object]]]
) -> None:
    await user_factory(email="login2@example.com", password="secret123")
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "login2@example.com", "password": "wrong"},
    )
    assert response.status_code == 401


async def test_me_with_token_returns_user(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/users/me")
    assert response.status_code == 200
    assert response.json()["email"] == "auth@example.com"
