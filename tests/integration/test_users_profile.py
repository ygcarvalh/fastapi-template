from collections.abc import Awaitable, Callable

from httpx import AsyncClient

UserFactory = Callable[..., Awaitable[dict[str, object]]]


async def test_the_profile_accepts_a_name(auth_client: AsyncClient) -> None:
    response = await auth_client.patch("/api/v1/users/me", json={"name": "Ada"})

    assert response.status_code == 200
    assert response.json()["name"] == "Ada"


async def test_the_profile_accepts_a_new_address(auth_client: AsyncClient) -> None:
    response = await auth_client.patch(
        "/api/v1/users/me", json={"email": "moved@example.com"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == "moved@example.com"


async def test_a_taken_address_is_refused(
    auth_client: AsyncClient, user_factory: UserFactory
) -> None:
    await user_factory(email="taken@example.com", password="secret123")

    response = await auth_client.patch(
        "/api/v1/users/me", json={"email": "taken@example.com"}
    )

    assert response.status_code == 409
    assert response.json()["message"] == "Email already registered"


async def test_the_password_changes_and_the_old_one_stops_working(
    auth_client: AsyncClient,
) -> None:
    changed = await auth_client.post(
        "/api/v1/auth/password",
        json={"current_password": "secret123", "new_password": "brand-new-secret"},
    )

    assert changed.status_code == 204

    refused = await auth_client.post(
        "/api/v1/auth/login",
        data={"username": "auth@example.com", "password": "secret123"},
    )
    accepted = await auth_client.post(
        "/api/v1/auth/login",
        data={"username": "auth@example.com", "password": "brand-new-secret"},
    )

    assert refused.status_code == 401
    assert accepted.status_code == 200


async def test_the_current_password_is_required(auth_client: AsyncClient) -> None:
    response = await auth_client.post(
        "/api/v1/auth/password",
        json={"current_password": "not-the-one", "new_password": "brand-new-secret"},
    )

    assert response.status_code == 403
    assert response.json()["message"] == "Current password is incorrect"


async def test_changing_the_password_needs_a_token(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/password",
        json={"current_password": "secret123", "new_password": "brand-new-secret"},
    )

    assert response.status_code == 401
