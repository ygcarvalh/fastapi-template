from collections.abc import Awaitable, Callable

from httpx import AsyncClient

UserFactory = Callable[..., Awaitable[dict[str, object]]]

PASSWORD = "secret123"


async def test_a_registered_address_is_stored_in_lowercase(
    user_factory: UserFactory,
) -> None:
    created = await user_factory(email="Mixed.Case@Example.COM", password=PASSWORD)

    assert created["email"] == "mixed.case@example.com"


async def test_signing_in_ignores_the_case_of_the_address(
    client: AsyncClient, user_factory: UserFactory
) -> None:
    await user_factory(email="reader@example.com", password=PASSWORD)

    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "Reader@Example.com", "password": PASSWORD},
    )

    assert response.status_code == 200


async def test_the_same_address_in_another_case_is_a_conflict(
    client: AsyncClient, user_factory: UserFactory
) -> None:
    await user_factory(email="taken@example.com", password=PASSWORD)

    response = await client.post(
        "/api/v1/users", json={"email": "TAKEN@example.com", "password": PASSWORD}
    )

    assert response.status_code == 409


async def test_a_profile_update_lowercases_the_new_address(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.patch(
        "/api/v1/users/me", json={"email": "Renamed@Example.com"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == "renamed@example.com"
