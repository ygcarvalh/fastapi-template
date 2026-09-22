from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage.local import LocalStorage
from app.models.item import Item
from app.models.user import User
from app.repositories.attachment_repo import AttachmentRepository
from app.repositories.item_repo import ItemRepository
from app.services.attachment_service import AttachmentService, Upload

ALLOWED = frozenset({"text/plain"})


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


async def _owned_item(session: AsyncSession) -> tuple[User, Item]:
    user = User(email="owner@example.com", hashed_password="hashed")
    session.add(user)
    await session.flush()
    item = Item(title="holder", owner_id=user.id)
    session.add(item)
    await session.flush()
    return user, item


def _service(session: AsyncSession, tmp_path: Path) -> AttachmentService:
    return AttachmentService(
        AttachmentRepository(session),
        ItemRepository(session),
        LocalStorage(tmp_path),
        session,
        max_bytes=1024,
        allowed_types=ALLOWED,
    )


async def test_a_rollback_after_add_leaves_no_orphan_file(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    user, item = await _owned_item(db_session)
    service = _service(db_session, tmp_path)

    stored = await service.add(
        item.id, user.id, Upload("notes.txt", "text/plain", _chunks(b"hello"))
    )
    assert (tmp_path / stored.key).exists()

    await db_session.rollback()
    await service.await_background_cleanup()

    assert not (tmp_path / stored.key).exists()


async def test_a_rollback_after_remove_keeps_the_row_and_file(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    user, item = await _owned_item(db_session)
    owner_id = user.id
    service = _service(db_session, tmp_path)

    stored = await service.add(
        item.id, owner_id, Upload("notes.txt", "text/plain", _chunks(b"hello"))
    )
    attachment_id, key = stored.id, stored.key
    await db_session.commit()
    assert (tmp_path / key).exists()

    await service.remove(attachment_id, owner_id)
    assert (tmp_path / key).exists()

    await db_session.rollback()
    await service.await_background_cleanup()

    assert (tmp_path / key).exists()
    restored = await AttachmentRepository(db_session).get_for_owner(
        attachment_id, owner_id
    )
    assert restored is not None
