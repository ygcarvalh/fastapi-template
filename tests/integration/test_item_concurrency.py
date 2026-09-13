from httpx import AsyncClient, Response

TITLE = {"title": "first"}


async def _create(client: AsyncClient) -> Response:
    return await client.post("/api/v1/items", json=TITLE)


async def test_a_read_hands_back_the_version_to_write_against(
    auth_client: AsyncClient,
) -> None:
    created = await _create(auth_client)
    item_id = created.json()["id"]

    read = await auth_client.get(f"/api/v1/items/{item_id}")

    assert created.headers["etag"] == 'W/"1"'
    assert read.headers["etag"] == 'W/"1"'
    assert read.json()["version"] == 1


async def test_a_write_without_if_match_is_refused(auth_client: AsyncClient) -> None:
    item_id = (await _create(auth_client)).json()["id"]

    response = await auth_client.patch(
        f"/api/v1/items/{item_id}", json={"title": "second"}
    )

    assert response.status_code == 428
    assert response.json()["code"] == "error.preconditionRequired"


async def test_a_write_against_a_stale_version_is_refused(
    auth_client: AsyncClient,
) -> None:
    created = await _create(auth_client)
    item_id = created.json()["id"]
    await auth_client.patch(
        f"/api/v1/items/{item_id}",
        json={"title": "second"},
        headers={"If-Match": created.headers["etag"]},
    )

    late = await auth_client.patch(
        f"/api/v1/items/{item_id}",
        json={"title": "third"},
        headers={"If-Match": created.headers["etag"]},
    )

    assert late.status_code == 412
    body = late.json()
    assert body["code"] == "error.versionConflict"
    assert body["params"] == {"expected": 1, "current": 2}
    assert (await auth_client.get(f"/api/v1/items/{item_id}")).json()["title"] == (
        "second"
    )


async def test_a_write_bumps_the_version_it_answers_with(
    auth_client: AsyncClient,
) -> None:
    created = await _create(auth_client)
    item_id = created.json()["id"]

    updated = await auth_client.patch(
        f"/api/v1/items/{item_id}",
        json={"title": "second"},
        headers={"If-Match": created.headers["etag"]},
    )

    assert updated.json()["version"] == 2
    assert updated.headers["etag"] == 'W/"2"'


async def test_a_star_if_match_writes_against_whatever_is_there(
    auth_client: AsyncClient,
) -> None:
    item_id = (await _create(auth_client)).json()["id"]

    response = await auth_client.patch(
        f"/api/v1/items/{item_id}", json={"title": "second"}, headers={"If-Match": "*"}
    )

    assert response.status_code == 200


async def test_an_unreadable_if_match_is_refused(auth_client: AsyncClient) -> None:
    item_id = (await _create(auth_client)).json()["id"]

    response = await auth_client.patch(
        f"/api/v1/items/{item_id}",
        json={"title": "second"},
        headers={"If-Match": 'W/"not-a-version"'},
    )

    assert response.status_code == 412


async def test_a_delete_against_a_stale_version_is_refused(
    auth_client: AsyncClient,
) -> None:
    created = await _create(auth_client)
    item_id = created.json()["id"]
    await auth_client.patch(
        f"/api/v1/items/{item_id}",
        json={"title": "second"},
        headers={"If-Match": created.headers["etag"]},
    )

    response = await auth_client.delete(
        f"/api/v1/items/{item_id}", headers={"If-Match": created.headers["etag"]}
    )

    assert response.status_code == 412
    assert (await auth_client.get(f"/api/v1/items/{item_id}")).status_code == 200
