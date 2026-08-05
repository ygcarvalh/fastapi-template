from collections.abc import Sequence

from app.core.exceptions import NotFoundError
from app.models.item import Item
from app.repositories.item_repo import ItemRepository
from app.schemas.item import ItemCreate, ItemUpdate


class ItemService:
    def __init__(self, repo: ItemRepository) -> None:
        self._repo = repo

    async def list_for_owner(self, owner_id: int) -> Sequence[Item]:
        return await self._repo.list_for_owner(owner_id)

    async def create(self, owner_id: int, data: ItemCreate) -> Item:
        item = Item(title=data.title, description=data.description, owner_id=owner_id)
        return await self._repo.create(item)

    async def get_for_owner(self, item_id: int, owner_id: int) -> Item:
        item = await self._repo.get_for_owner(item_id, owner_id)
        if item is None:
            raise NotFoundError("Item not found")
        return item

    async def update(self, item_id: int, owner_id: int, data: ItemUpdate) -> Item:
        item = await self.get_for_owner(item_id, owner_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(item, field, value)
        return item

    async def delete(self, item_id: int, owner_id: int) -> None:
        item = await self.get_for_owner(item_id, owner_id)
        await self._repo.delete(item)
