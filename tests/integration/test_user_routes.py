from collections.abc import Awaitable, Callable

from httpx import AsyncClient


async def test_register_user_returns_201(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/users", json={"email": "new@example.com", "password": "secret123"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert "id" in body
    assert "password" not in body


async def test_register_duplicate_returns_409(
    client: AsyncClient, user_factory: Callable[..., Awaitable[dict[str, object]]]
) -> None:
    await user_factory(email="dup@example.com")
    response = await client.post(
        "/api/v1/users", json={"email": "dup@example.com", "password": "secret123"}
    )
    assert response.status_code == 409


async def test_me_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
