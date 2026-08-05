from collections.abc import Awaitable, Callable

from httpx import AsyncClient


async def test_items_require_auth(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/items")).status_code == 401


async def test_create_and_list_item(auth_client: AsyncClient) -> None:
    created = await auth_client.post("/api/v1/items", json={"title": "Task one"})
    assert created.status_code == 201
    item = created.json()
    assert item["title"] == "Task one"

    listing = await auth_client.get("/api/v1/items")
    assert listing.status_code == 200
    assert [i["id"] for i in listing.json()] == [item["id"]]


async def test_update_item(auth_client: AsyncClient) -> None:
    item_id = (await auth_client.post("/api/v1/items", json={"title": "old"})).json()[
        "id"
    ]
    response = await auth_client.patch(
        f"/api/v1/items/{item_id}", json={"title": "new"}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "new"


async def test_patch_clears_description_when_explicitly_null(
    auth_client: AsyncClient,
) -> None:
    created = await auth_client.post(
        "/api/v1/items", json={"title": "documented", "description": "some text"}
    )
    item_id = created.json()["id"]
    assert created.json()["description"] == "some text"

    response = await auth_client.patch(
        f"/api/v1/items/{item_id}", json={"description": None}
    )
    assert response.status_code == 200
    assert response.json()["description"] is None


async def test_patch_leaves_omitted_description_untouched(
    auth_client: AsyncClient,
) -> None:
    created = await auth_client.post(
        "/api/v1/items", json={"title": "documented", "description": "some text"}
    )
    item_id = created.json()["id"]

    response = await auth_client.patch(
        f"/api/v1/items/{item_id}", json={"title": "retitled"}
    )
    assert response.status_code == 200
    assert response.json()["title"] == "retitled"
    assert response.json()["description"] == "some text"


async def test_patch_rejects_null_title(auth_client: AsyncClient) -> None:
    item_id = (await auth_client.post("/api/v1/items", json={"title": "keep"})).json()[
        "id"
    ]

    response = await auth_client.patch(f"/api/v1/items/{item_id}", json={"title": None})
    assert response.status_code == 422


async def test_delete_item(auth_client: AsyncClient) -> None:
    item_id = (await auth_client.post("/api/v1/items", json={"title": "gone"})).json()[
        "id"
    ]
    assert (await auth_client.delete(f"/api/v1/items/{item_id}")).status_code == 204
    assert (await auth_client.get(f"/api/v1/items/{item_id}")).status_code == 404


async def test_cannot_access_other_users_item(
    auth_client: AsyncClient,
    client: AsyncClient,
    user_factory: Callable[..., Awaitable[dict[str, object]]],
) -> None:
    item_id = (await auth_client.post("/api/v1/items", json={"title": "mine"})).json()[
        "id"
    ]
    await user_factory(email="other@example.com", password="secret123")
    login = await client.post(
        "/api/v1/auth/login",
        data={"username": "other@example.com", "password": "secret123"},
    )
    other_token = login.json()["access_token"]
    response = await client.get(
        f"/api/v1/items/{item_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 404
