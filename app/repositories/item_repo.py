from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item


class ItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_owner(
        self, owner_id: int, limit: int, offset: int
    ) -> Sequence[Item]:
        result = await self._session.execute(
            select(Item)
            .where(Item.owner_id == owner_id)
            .order_by(Item.id)
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def count_for_owner(self, owner_id: int) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Item).where(Item.owner_id == owner_id)
        )
        return result.scalar_one()

    async def get_for_owner(self, item_id: int, owner_id: int) -> Item | None:
        result = await self._session.execute(
            select(Item).where(Item.id == item_id, Item.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def create(self, item: Item) -> Item:
        self._session.add(item)
        await self._session.flush()
        await self._session.refresh(item)
        return item

    async def delete(self, item: Item) -> None:
        await self._session.delete(item)
        await self._session.flush()
