from collections.abc import AsyncIterator, Sequence
from pathlib import Path

import pytest

from app.core.exceptions import ForbiddenError, NotFoundError, PayloadTooLargeError
from app.core.storage.local import LocalStorage
from app.models.attachment import Attachment
from app.models.item import Item
from app.services.attachment_service import (
    AttachmentService,
    Upload,
    safe_filename,
)
from tests.unit.fakes import FakeItemRepository

OWNER_ID = 1
OTHER_OWNER_ID = 2
ALLOWED = frozenset({"text/plain"})


class FakeAttachmentRepository:
    def __init__(self) -> None:
        self.stored: list[Attachment] = []
        self.deleted: list[Attachment] = []

    async def create(self, attachment: Attachment) -> Attachment:
        attachment.id = len(self.stored) + 1
        self.stored.append(attachment)
        return attachment

    async def list_for_item(self, item_id: int) -> Sequence[Attachment]:
        return [entry for entry in self.stored if entry.item_id == item_id]

    async def get_for_owner(
        self, attachment_id: int, owner_id: int
    ) -> Attachment | None:
        return next((entry for entry in self.stored if entry.id == attachment_id), None)

    async def delete(self, attachment: Attachment) -> None:
        self.stored.remove(attachment)
        self.deleted.append(attachment)


def _stored_names(root: Path) -> list[str]:
    return sorted(entry.name for entry in root.iterdir())


def _stored_bytes(root: Path, key: str) -> bytes:
    return (root / key).read_bytes()


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


def _owned_item() -> Item:
    item = Item(title="holder", owner_id=OWNER_ID)
    item.id = 1
    return item


def _service(
    tmp_path: Path, max_bytes: int = 1024
) -> tuple[AttachmentService, FakeAttachmentRepository]:
    repo = FakeAttachmentRepository()
    service = AttachmentService(
        repo,
        FakeItemRepository([_owned_item()]),
        LocalStorage(tmp_path),
        max_bytes=max_bytes,
        allowed_types=ALLOWED,
    )
    return service, repo


async def test_an_upload_is_stored_under_a_generated_key(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    stored = await service.add(
        1, OWNER_ID, Upload("notes.txt", "text/plain", _chunks(b"hello"))
    )

    assert stored.key != "notes.txt"
    assert stored.size_bytes == 5
    assert _stored_bytes(tmp_path, stored.key) == b"hello"


async def test_the_content_type_is_read_without_its_parameters(
    tmp_path: Path,
) -> None:
    service, _ = _service(tmp_path)

    stored = await service.add(
        1, OWNER_ID, Upload("notes.txt", "text/plain; charset=utf-8", _chunks(b"hi"))
    )

    assert stored.content_type == "text/plain"


async def test_a_type_this_deployment_refuses_never_reaches_disk(
    tmp_path: Path,
) -> None:
    service, _ = _service(tmp_path)

    with pytest.raises(ForbiddenError) as raised:
        await service.add(
            1, OWNER_ID, Upload("run.sh", "application/x-sh", _chunks(b"rm -rf /"))
        )

    assert raised.value.code == "attachment.typeRefused"
    assert _stored_names(tmp_path) == []


async def test_a_file_over_the_limit_is_refused_and_swept(tmp_path: Path) -> None:
    service, repo = _service(tmp_path, max_bytes=4)

    with pytest.raises(PayloadTooLargeError) as raised:
        await service.add(
            1, OWNER_ID, Upload("big.txt", "text/plain", _chunks(b"12", b"34", b"56"))
        )

    assert raised.value.params == {"limit": 4}
    assert repo.stored == []
    assert _stored_names(tmp_path) == []


async def test_another_account_cannot_attach_to_an_item(tmp_path: Path) -> None:
    service, _ = _service(tmp_path)

    with pytest.raises(NotFoundError):
        await service.add(
            1, OTHER_OWNER_ID, Upload("notes.txt", "text/plain", _chunks(b"hi"))
        )


async def test_removing_an_attachment_drops_the_file_too(tmp_path: Path) -> None:
    service, repo = _service(tmp_path)
    stored = await service.add(
        1, OWNER_ID, Upload("notes.txt", "text/plain", _chunks(b"hello"))
    )

    await service.remove(stored.id, OWNER_ID)

    assert repo.stored == []
    assert _stored_names(tmp_path) == []


async def test_reading_an_attachment_hands_back_what_was_stored(
    tmp_path: Path,
) -> None:
    service, _ = _service(tmp_path)
    stored = await service.add(
        1, OWNER_ID, Upload("notes.txt", "text/plain", _chunks(b"hello"))
    )

    read = b"".join([chunk async for chunk in service.read(stored)])

    assert read == b"hello"


@pytest.mark.parametrize(
    ("sent", "expected"),
    [
        ("../../etc/passwd", "passwd"),
        ("C:\\Windows\\system32\\cmd.exe", "cmd.exe"),
        ("", "file"),
        (None, "file"),
        ("   ", "file"),
        ("report.pdf", "report.pdf"),
    ],
)
def test_a_filename_is_reduced_to_a_plain_name(sent: str | None, expected: str) -> None:
    assert safe_filename(sent) == expected


def test_a_very_long_filename_is_cut_to_what_the_column_holds() -> None:
    assert len(safe_filename("a" * 400)) == 255


@pytest.mark.parametrize(
    ("sent", "refused"),
    [
        ('quote".pdf', '"'),
        ("back\\slash.pdf", "\\"),
        ("semi;colon.pdf", ";"),
        ("line\r\nbreak.pdf", "\n"),
    ],
)
def test_a_filename_drops_what_would_break_a_header(sent: str, refused: str) -> None:
    assert refused not in safe_filename(sent)
