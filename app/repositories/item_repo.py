from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import PreconditionFailedError
from app.models.item import Item

ACTIVE = Item.deleted_at.is_(None)
LOST_UPDATE = "This item changed while you were editing it"


class ItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_owner(
        self, owner_id: int, limit: int, offset: int
    ) -> Sequence[Item]:
        result = await self._session.execute(
            select(Item)
            .where(Item.owner_id == owner_id, ACTIVE)
            .order_by(Item.id)
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def count_for_owner(self, owner_id: int) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Item)
            .where(Item.owner_id == owner_id, ACTIVE)
        )
        return result.scalar_one()

    async def get_for_owner(self, item_id: int, owner_id: int) -> Item | None:
        result = await self._session.execute(
            select(Item).where(Item.id == item_id, Item.owner_id == owner_id, ACTIVE)
        )
        return result.scalar_one_or_none()

    async def create(self, item: Item) -> Item:
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def save(self, item: Item) -> Item:
        await self._flush()
        await self._session.refresh(item)
        return item

    async def soft_delete(self, item: Item) -> None:
        item.mark_deleted()
        await self._flush()

    async def _flush(self) -> None:
        try:
            await self._session.flush()
        except StaleDataError as error:
            raise PreconditionFailedError(LOST_UPDATE) from error

    async def soft_delete_for_owner(self, owner_id: int) -> None:
        owned = await self._session.execute(
            select(Item).where(Item.owner_id == owner_id, ACTIVE)
        )
        for item in owned.scalars().all():
            item.mark_deleted()
        await self._session.flush()
