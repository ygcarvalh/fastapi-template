import asyncio
from collections.abc import AsyncIterator, Sequence
from pathlib import PurePosixPath
from typing import NamedTuple
from uuid import uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import (
    ForbiddenError,
    PayloadTooLargeError,
)
from app.core.storage.backend import Storage
from app.db.transactional_hooks import run_after_outcome
from app.models.attachment import Attachment
from app.services.protocols import (
    AttachmentRepositoryProtocol,
    ItemRepositoryProtocol,
)
from app.services.support import or_not_found

logger = structlog.stdlib.get_logger("app.attachments")

FALLBACK_FILENAME = "file"
MAX_FILENAME_LENGTH = 255
REFUSED_IN_FILENAME = frozenset({'"', "\\", ";", "\r", "\n"})
TOO_LARGE = "This file is larger than the deployment accepts"
TYPE_REFUSED = "This deployment does not accept that file type"


class Upload(NamedTuple):
    filename: str | None
    content_type: str | None
    chunks: AsyncIterator[bytes]


def safe_filename(name: str | None) -> str:
    candidate = PurePosixPath((name or "").replace("\\", "/")).name
    cleaned = "".join(
        character
        for character in candidate
        if character.isprintable() and character not in REFUSED_IN_FILENAME
    ).strip()
    return (cleaned or FALLBACK_FILENAME)[:MAX_FILENAME_LENGTH]


class AttachmentService:
    def __init__(
        self,
        repo: AttachmentRepositoryProtocol,
        items: ItemRepositoryProtocol,
        storage: Storage,
        session: AsyncSession,
        *,
        max_bytes: int,
        allowed_types: frozenset[str],
    ) -> None:
        self._repo = repo
        self._items = items
        self._storage = storage
        self._session = session
        self._max_bytes = max_bytes
        self._allowed_types = allowed_types
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def add(self, item_id: int, owner_id: int, upload: Upload) -> Attachment:
        await self._owned_item(item_id, owner_id)
        content_type = (upload.content_type or "").split(";")[0].strip()
        if content_type not in self._allowed_types:
            raise ForbiddenError(
                TYPE_REFUSED,
                code=ErrorCode.ATTACHMENT_TYPE_REFUSED,
                params={"type": content_type or "unknown"},
            )

        key = uuid4().hex
        stored = await self._storage.save(key, self._bounded(upload.chunks, key))
        # Registered before the insert, not after: if the row insert itself
        # raises (FK violation, a concurrently deleted item, ...), the
        # request still rolls back and this listener must already be in
        # place to clean up the blob that made it to disk. A listener that
        # fires for a row that was never created is harmless.
        self._delete_key_on_rollback(stored.key)
        return await self._repo.create(
            Attachment(
                key=stored.key,
                filename=safe_filename(upload.filename),
                content_type=content_type,
                size_bytes=stored.size_bytes,
                item_id=item_id,
            )
        )

    async def list_for_item(self, item_id: int, owner_id: int) -> Sequence[Attachment]:
        await self._owned_item(item_id, owner_id)
        return await self._repo.list_for_item(item_id)

    async def get_for_owner(self, attachment_id: int, owner_id: int) -> Attachment:
        return or_not_found(
            await self._repo.get_for_owner(attachment_id, owner_id),
            "Attachment not found",
            ErrorCode.ATTACHMENT_NOT_FOUND,
        )

    def read(self, attachment: Attachment) -> AsyncIterator[bytes]:
        return self._storage.open(attachment.key)

    async def remove(self, attachment_id: int, owner_id: int) -> None:
        stored = await self.get_for_owner(attachment_id, owner_id)
        await self._repo.delete(stored)
        self._delete_key_on_commit(stored.key)

    async def _owned_item(self, item_id: int, owner_id: int) -> None:
        or_not_found(
            await self._items.get_for_owner(item_id, owner_id),
            "Item not found",
            ErrorCode.ITEM_NOT_FOUND,
        )

    async def _bounded(
        self, chunks: AsyncIterator[bytes], key: str
    ) -> AsyncIterator[bytes]:
        written = 0
        async for chunk in chunks:
            written += len(chunk)
            if written > self._max_bytes:
                await self._storage.delete(key)
                raise PayloadTooLargeError(
                    TOO_LARGE,
                    code=ErrorCode.ATTACHMENT_TOO_LARGE,
                    params={"limit": self._max_bytes},
                )
            yield chunk

    def _delete_key_on_rollback(self, key: str) -> None:
        run_after_outcome(self._session, on_rollback=lambda: self._schedule_delete(key))

    def _delete_key_on_commit(self, key: str) -> None:
        run_after_outcome(self._session, on_commit=lambda: self._schedule_delete(key))

    def _schedule_delete(self, key: str) -> None:
        task = asyncio.get_running_loop().create_task(self._delete_quietly(key))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def _delete_quietly(self, key: str) -> None:
        try:
            await self._storage.delete(key)
        except Exception:
            logger.warning("attachment_cleanup_failed", key=key, exc_info=True)

    async def await_background_cleanup(self) -> None:
        await asyncio.gather(*self._background_tasks)
