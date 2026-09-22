from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm.exc import StaleDataError

from app.core.exceptions import PreconditionFailedError
from app.models.item import Item
from app.repositories.base import CrudRepository, SoftDeleteRepository

LOST_UPDATE = "This item changed while you were editing it"


class ItemRepository(CrudRepository[Item], SoftDeleteRepository[Item]):
    _model = Item

    async def list_for_owner(
        self, owner_id: int, limit: int, offset: int
    ) -> Sequence[Item]:
        return await self._all(
            select(Item)
            .where(Item.owner_id == owner_id, Item.is_active())
            .order_by(Item.id)
            .limit(limit)
            .offset(offset)
        )

    async def count_for_owner(self, owner_id: int) -> int:
        return await self._one(
            select(func.count())
            .select_from(Item)
            .where(Item.owner_id == owner_id, Item.is_active())
        )

    async def get_for_owner(self, item_id: int, owner_id: int) -> Item | None:
        return await self._one_or_none(
            select(Item).where(
                Item.id == item_id, Item.owner_id == owner_id, Item.is_active()
            )
        )

    async def _flush(self) -> None:
        try:
            await self._session.flush()
        except StaleDataError as error:
            raise PreconditionFailedError(LOST_UPDATE) from error

    async def soft_delete_for_owner(self, owner_id: int) -> None:
        owned = await self._all(
            select(Item).where(Item.owner_id == owner_id, Item.is_active())
        )
        for item in owned:
            item.mark_deleted()
        await self._flush()
