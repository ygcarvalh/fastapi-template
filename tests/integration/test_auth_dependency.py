from httpx import AsyncClient

from app.core.security import create_access_token

DELETED_USER_ID = 999_999


async def test_token_with_a_non_numeric_subject_is_rejected(
    client: AsyncClient,
) -> None:
    token = create_access_token("not-a-user-id")

    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


async def test_token_for_a_missing_user_is_rejected(client: AsyncClient) -> None:
    token = create_access_token(str(DELETED_USER_ID))

    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401


async def test_malformed_authorization_header_is_rejected(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": "Basic bm9wZQ=="}
    )

    assert response.status_code == 401
