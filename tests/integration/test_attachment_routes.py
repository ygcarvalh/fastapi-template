from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.storage.local import LocalStorage

TEXT = ("notes.txt", b"hello world", "text/plain")


@pytest.fixture(autouse=True)
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setattr("app.api.deps.get_storage", lambda: LocalStorage(tmp_path))
    yield tmp_path


async def _item(client: AsyncClient) -> int:
    created = await client.post("/api/v1/items", json={"title": "holder"})
    return int(created.json()["id"])


async def test_a_file_can_be_attached_and_listed(auth_client: AsyncClient) -> None:
    item_id = await _item(auth_client)

    uploaded = await auth_client.post(
        f"/api/v1/items/{item_id}/attachments", files={"file": TEXT}
    )
    listing = await auth_client.get(f"/api/v1/items/{item_id}/attachments")

    assert uploaded.status_code == 201
    assert uploaded.json()["filename"] == "notes.txt"
    assert uploaded.json()["size_bytes"] == 11
    assert [entry["id"] for entry in listing.json()] == [uploaded.json()["id"]]


async def test_a_file_comes_back_byte_for_byte(auth_client: AsyncClient) -> None:
    item_id = await _item(auth_client)
    uploaded = await auth_client.post(
        f"/api/v1/items/{item_id}/attachments", files={"file": TEXT}
    )

    response = await auth_client.get(
        f"/api/v1/attachments/{uploaded.json()['id']}/content"
    )

    assert response.content == b"hello world"
    assert response.headers["content-disposition"] == 'attachment; filename="notes.txt"'


async def test_a_type_this_deployment_refuses_is_answered_with_403(
    auth_client: AsyncClient,
) -> None:
    item_id = await _item(auth_client)

    response = await auth_client.post(
        f"/api/v1/items/{item_id}/attachments",
        files={"file": ("run.sh", b"rm -rf /", "application/x-sh")},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "attachment.typeRefused"


async def test_attaching_to_an_item_that_is_not_yours_reads_as_missing(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.post(
        "/api/v1/items/999999/attachments", files={"file": TEXT}
    )

    assert response.status_code == 404


async def test_a_removed_attachment_is_gone_from_the_listing(
    auth_client: AsyncClient,
) -> None:
    item_id = await _item(auth_client)
    uploaded = await auth_client.post(
        f"/api/v1/items/{item_id}/attachments", files={"file": TEXT}
    )

    removed = await auth_client.delete(f"/api/v1/attachments/{uploaded.json()['id']}")

    assert removed.status_code == 204
    listing = await auth_client.get(f"/api/v1/items/{item_id}/attachments")
    assert listing.json() == []


async def test_attachments_need_a_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/items/1/attachments")

    assert response.status_code == 401
