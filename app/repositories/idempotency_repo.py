from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency_key import IdempotencyKey


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int, key: str) -> IdempotencyKey | None:
        result = await self._session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == user_id, IdempotencyKey.key == key
            )
        )
        return result.scalar_one_or_none()

    async def claim(self, entry: IdempotencyKey) -> IdempotencyKey | None:
        savepoint = await self._session.begin_nested()
        self._session.add(entry)
        try:
            await savepoint.commit()
        except IntegrityError:
            await savepoint.rollback()
            self._session.expunge(entry)
            return None
        return entry

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
        await self._session.flush()

    async def release(self, entry: IdempotencyKey) -> None:
        await self._session.delete(entry)
        await self._session.flush()

    async def delete_batch_created_before(
        self, cutoff: datetime, batch_size: int
    ) -> int:
        doomed = (
            select(IdempotencyKey.id)
            .where(IdempotencyKey.created_at < cutoff)
            .order_by(IdempotencyKey.id)
            .limit(batch_size)
            .scalar_subquery()
        )
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                delete(IdempotencyKey).where(IdempotencyKey.id.in_(doomed))
            ),
        )
        return result.rowcount
