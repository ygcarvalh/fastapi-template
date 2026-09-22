from collections.abc import Sequence

from app.core.error_codes import ErrorCode
from app.core.exceptions import PreconditionFailedError
from app.models.item import Item
from app.schemas.item import ItemCreate, ItemUpdate
from app.services.protocols import ItemRepositoryProtocol
from app.services.support import or_not_found

STALE_READ = "This item changed since you read it"


class ItemService:
    def __init__(self, repo: ItemRepositoryProtocol) -> None:
        self._repo = repo

    async def list_for_owner(
        self, owner_id: int, limit: int, offset: int
    ) -> tuple[Sequence[Item], int]:
        items = await self._repo.list_for_owner(owner_id, limit, offset)
        total = await self._repo.count_for_owner(owner_id)
        return items, total

    async def create(self, owner_id: int, data: ItemCreate) -> Item:
        item = Item(title=data.title, description=data.description, owner_id=owner_id)
        return await self._repo.create(item)

    async def get_for_owner(self, item_id: int, owner_id: int) -> Item:
        return or_not_found(
            await self._repo.get_for_owner(item_id, owner_id),
            "Item not found",
            ErrorCode.ITEM_NOT_FOUND,
        )

    async def update(
        self,
        item_id: int,
        owner_id: int,
        data: ItemUpdate,
        expected_version: int | None = None,
    ) -> Item:
        item = await self._at_version(item_id, owner_id, expected_version)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(item, field, value)
        return await self._repo.save(item)

    async def delete(
        self, item_id: int, owner_id: int, expected_version: int | None = None
    ) -> None:
        item = await self._at_version(item_id, owner_id, expected_version)
        await self._repo.soft_delete(item)

    async def _at_version(
        self, item_id: int, owner_id: int, expected_version: int | None
    ) -> Item:
        item = await self.get_for_owner(item_id, owner_id)
        if expected_version is not None and item.version != expected_version:
            raise PreconditionFailedError(
                STALE_READ,
                params={"expected": expected_version, "current": item.version},
            )
        return item
