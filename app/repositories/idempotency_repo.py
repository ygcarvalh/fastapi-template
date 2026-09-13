from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.idempotency_key import IdempotencyKey
from app.repositories.base import BaseRepository


class IdempotencyRepository(BaseRepository):
    async def get(self, user_id: int, key: str) -> IdempotencyKey | None:
        return await self._one_or_none(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user_id, IdempotencyKey.key == key
            )
        )

    async def claim(self, entry: IdempotencyKey) -> IdempotencyKey | None:
        savepoint = await self._session.begin_nested()
        self._session.add(entry)
        try:
            await savepoint.commit()
        except IntegrityError:
            await savepoint.rollback()
            if entry in self._session:
                self._session.expunge(entry)
            return None
        return entry

    async def restart(
        self, entry: IdempotencyKey, request_hash: str, now: datetime
    ) -> None:
        entry.request_hash = request_hash
        entry.created_at = now
        entry.status_code = None
        entry.response_body = None
        entry.content_type = None
        entry.completed_at = None
        await self._flush()

    async def complete(
        self,
        entry: IdempotencyKey,
        *,
        status_code: int,
        body: str,
        content_type: str | None,
        completed_at: datetime,
    ) -> None:
        entry.status_code = status_code
        entry.response_body = body
        entry.content_type = content_type
        entry.completed_at = completed_at
        await self._flush()

    async def release(self, entry: IdempotencyKey) -> None:
        await self._remove(entry)

    async def delete_batch_created_before(
        self, cutoff: datetime, batch_size: int
    ) -> int:
        return await self._delete_batch_before(
            IdempotencyKey.id, IdempotencyKey.created_at, cutoff, batch_size
        )
