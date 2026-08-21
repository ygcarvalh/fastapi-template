from httpx import AsyncClient


async def test_an_account_starts_on_the_defaults(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/users/me/preferences")

    assert response.status_code == 200
    assert response.json() == {
        "locale": "en-US",
        "theme": "system",
        "show_request_id": True,
    }


async def test_a_change_is_stored_and_read_back(auth_client: AsyncClient) -> None:
    saved = await auth_client.patch(
        "/api/v1/users/me/preferences",
        json={"locale": "pt-BR", "theme": "dark", "show_request_id": False},
    )
    read = await auth_client.get("/api/v1/users/me/preferences")

    assert saved.status_code == 200
    assert read.json() == {"locale": "pt-BR", "theme": "dark", "show_request_id": False}


async def test_a_second_change_keeps_the_same_row(auth_client: AsyncClient) -> None:
    await auth_client.patch("/api/v1/users/me/preferences", json={"locale": "pt-BR"})
    second = await auth_client.patch(
        "/api/v1/users/me/preferences", json={"theme": "light"}
    )

    assert second.json() == {
        "locale": "pt-BR",
        "theme": "light",
        "show_request_id": True,
    }


async def test_an_unknown_theme_is_refused(auth_client: AsyncClient) -> None:
    response = await auth_client.patch(
        "/api/v1/users/me/preferences", json={"theme": "sepia"}
    )

    assert response.status_code == 422


async def test_a_forged_locale_is_refused(auth_client: AsyncClient) -> None:
    response = await auth_client.patch(
        "/api/v1/users/me/preferences", json={"locale": "en-US\ninjected"}
    )

    assert response.status_code == 422


async def test_preferences_need_a_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me/preferences")

    assert response.status_code == 401
