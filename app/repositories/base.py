from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, Executable, Select, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.db.mixins import SoftDeleteMixin

DELETE_BATCH_SIZE = 5000


class BaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _flush(self) -> None:
        await self._session.flush()

    async def _one_or_none[RowT](self, statement: Select[tuple[RowT]]) -> RowT | None:
        result = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def _one[RowT](self, statement: Select[tuple[RowT]]) -> RowT:
        result = await self._session.execute(statement)
        return result.scalar_one()

    async def _first[RowT](self, statement: Select[tuple[RowT]]) -> RowT | None:
        result = await self._session.execute(statement)
        return result.scalars().first()

    async def _all[RowT](self, statement: Select[tuple[RowT]]) -> Sequence[RowT]:
        result = await self._session.execute(statement)
        return result.scalars().all()

    async def _affected(self, statement: Executable) -> int:
        result = cast(CursorResult[Any], await self._session.execute(statement))
        return result.rowcount

    async def _insert[EntityT](self, entity: EntityT) -> EntityT:
        self._session.add(entity)
        await self._flush()
        return entity

    async def _insert_refreshed[EntityT](self, entity: EntityT) -> EntityT:
        await self._insert(entity)
        await self._session.refresh(entity)
        return entity

    async def _save[EntityT](self, entity: EntityT) -> EntityT:
        await self._flush()
        await self._session.refresh(entity)
        return entity

    async def _remove(self, entity: object) -> None:
        await self._session.delete(entity)
        await self._flush()

    # One statement per batch, so a retention run does not lock the table for
    # the length of a single enormous DELETE. The caller commits between calls.
    async def _delete_batch_before(
        self,
        identifier: InstrumentedAttribute[int],
        moment: InstrumentedAttribute[datetime],
        cutoff: datetime,
        batch_size: int = DELETE_BATCH_SIZE,
    ) -> int:
        doomed = (
            select(identifier)
            .where(moment < cutoff)
            .order_by(identifier)
            .limit(batch_size)
            .scalar_subquery()
        )
        return await self._affected(
            delete(identifier.class_).where(identifier.in_(doomed))
        )


class CrudRepository[ModelT](BaseRepository):
    _model: type[ModelT]

    async def get(self, entity_id: Any) -> ModelT | None:
        return await self._session.get(self._model, entity_id)

    async def create(self, entity: ModelT) -> ModelT:
        return await self._insert_refreshed(entity)

    async def save(self, entity: ModelT) -> ModelT:
        return await self._save(entity)

    async def delete(self, entity: ModelT) -> None:
        await self._remove(entity)


class SoftDeleteRepository[ModelT: SoftDeleteMixin](BaseRepository):
    async def soft_delete(self, entity: ModelT) -> None:
        entity.mark_deleted()
        await self._flush()
