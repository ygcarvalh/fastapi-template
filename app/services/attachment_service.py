import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import PurePosixPath
from typing import NamedTuple
from uuid import uuid4

import structlog
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession

from app.core.error_codes import ErrorCode
from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    PayloadTooLargeError,
)
from app.core.storage.backend import Storage
from app.models.attachment import Attachment
from app.services.protocols import (
    AttachmentRepositoryProtocol,
    ItemRepositoryProtocol,
)

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
        attachment = await self._repo.create(
            Attachment(
                key=stored.key,
                filename=safe_filename(upload.filename),
                content_type=content_type,
                size_bytes=stored.size_bytes,
                item_id=item_id,
            )
        )
        self._delete_key_on_rollback(stored.key)
        return attachment

    async def list_for_item(self, item_id: int, owner_id: int) -> Sequence[Attachment]:
        await self._owned_item(item_id, owner_id)
        return await self._repo.list_for_item(item_id)

    async def get_for_owner(self, attachment_id: int, owner_id: int) -> Attachment:
        stored = await self._repo.get_for_owner(attachment_id, owner_id)
        if stored is None:
            raise NotFoundError(
                "Attachment not found", code=ErrorCode.ATTACHMENT_NOT_FOUND
            )
        return stored

    def read(self, attachment: Attachment) -> AsyncIterator[bytes]:
        return self._storage.open(attachment.key)

    async def remove(self, attachment_id: int, owner_id: int) -> None:
        stored = await self.get_for_owner(attachment_id, owner_id)
        await self._repo.delete(stored)
        self._delete_key_on_commit(stored.key)

    async def _owned_item(self, item_id: int, owner_id: int) -> None:
        if await self._items.get_for_owner(item_id, owner_id) is None:
            raise NotFoundError("Item not found", code=ErrorCode.ITEM_NOT_FOUND)

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
        self._settle_key_on_next_outcome(key, delete_on="after_rollback")

    def _delete_key_on_commit(self, key: str) -> None:
        self._settle_key_on_next_outcome(key, delete_on="after_commit")

    def _settle_key_on_next_outcome(self, key: str, *, delete_on: str) -> None:
        # The transaction this key's fate depends on ends in exactly one of
        # `after_commit` or `after_rollback` — never both. Both hooks are
        # registered as a pair so whichever one the session actually fires
        # next retires the pair together; otherwise the hook we didn't act on
        # would linger on the session and could misfire against some later,
        # unrelated transaction (e.g. a second add()/remove() sharing this
        # same long-lived session).
        sync_session = self._session.sync_session

        def on_commit(session: SyncSession) -> None:
            self._deregister_pair(sync_session, on_commit, on_rollback)
            if delete_on == "after_commit":
                self._schedule_delete(key)

        def on_rollback(session: SyncSession) -> None:
            self._deregister_pair(sync_session, on_commit, on_rollback)
            if delete_on == "after_rollback":
                self._schedule_delete(key)

        event.listen(sync_session, "after_commit", on_commit)
        event.listen(sync_session, "after_rollback", on_rollback)

    @staticmethod
    def _deregister_pair(
        sync_session: SyncSession,
        on_commit: Callable[[SyncSession], None],
        on_rollback: Callable[[SyncSession], None],
    ) -> None:
        def _remove() -> None:
            event.remove(sync_session, "after_commit", on_commit)
            event.remove(sync_session, "after_rollback", on_rollback)

        # `event.remove` must not run while SQLAlchemy is still iterating the
        # listener deque for this very dispatch (it raises "deque mutated
        # during iteration"), so the removal is deferred to the next loop
        # iteration, once the dispatch that invoked this listener has
        # unwound.
        asyncio.get_running_loop().call_soon(_remove)

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
