from httpx import AsyncClient


async def test_an_account_starts_on_the_defaults(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/users/me/preferences")

    assert response.status_code == 200
    assert response.json() == {
        "locale": "en-US",
        "theme": "system",
        "show_request_id": True,
        "features": None,
    }


async def test_a_change_is_stored_and_read_back(auth_client: AsyncClient) -> None:
    saved = await auth_client.patch(
        "/api/v1/users/me/preferences",
        json={"locale": "pt-BR", "theme": "dark", "show_request_id": False},
    )
    read = await auth_client.get("/api/v1/users/me/preferences")

    assert saved.status_code == 200
    assert read.json() == {
        "locale": "pt-BR",
        "theme": "dark",
        "show_request_id": False,
        "features": None,
    }


async def test_a_second_change_keeps_the_same_row(auth_client: AsyncClient) -> None:
    await auth_client.patch("/api/v1/users/me/preferences", json={"locale": "pt-BR"})
    second = await auth_client.patch(
        "/api/v1/users/me/preferences", json={"theme": "light"}
    )

    assert second.json() == {
        "locale": "pt-BR",
        "theme": "light",
        "show_request_id": True,
        "features": None,
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


async def test_an_account_can_name_the_features_it_wants(
    auth_client: AsyncClient,
) -> None:
    chosen = await auth_client.patch(
        "/api/v1/users/me/preferences", json={"features": "notes"}
    )

    assert chosen.status_code == 200
    assert chosen.json()["features"] == "notes"


async def test_an_account_can_turn_every_feature_off(auth_client: AsyncClient) -> None:
    response = await auth_client.patch(
        "/api/v1/users/me/preferences", json={"features": ""}
    )

    assert response.json()["features"] == ""


async def test_null_hands_the_account_back_to_the_environment(
    auth_client: AsyncClient,
) -> None:
    await auth_client.patch("/api/v1/users/me/preferences", json={"features": ""})
    response = await auth_client.patch(
        "/api/v1/users/me/preferences", json={"features": None}
    )

    assert response.json()["features"] is None


async def test_a_forged_feature_list_is_refused(auth_client: AsyncClient) -> None:
    response = await auth_client.patch(
        "/api/v1/users/me/preferences", json={"features": "notes; drop table"}
    )

    assert response.status_code == 422
