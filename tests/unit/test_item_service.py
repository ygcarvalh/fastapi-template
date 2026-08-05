import pytest

from app.core.exceptions import NotFoundError
from app.models.item import Item
from app.schemas.item import ItemUpdate
from app.services.item_service import ItemService
from tests.unit.fakes import FakeItemRepository

OWNER_ID = 1
OTHER_OWNER_ID = 2


def _owned_item() -> Item:
    item = Item(title="old", description="old-desc", owner_id=OWNER_ID)
    item.id = 1
    return item


async def test_get_for_owner_missing_raises() -> None:
    service = ItemService(FakeItemRepository())

    with pytest.raises(NotFoundError):
        await service.get_for_owner(1, OWNER_ID)


async def test_get_for_owner_rejects_another_owners_item() -> None:
    service = ItemService(FakeItemRepository([_owned_item()]))

    with pytest.raises(NotFoundError):
        await service.get_for_owner(1, OTHER_OWNER_ID)


async def test_update_applies_only_provided_fields() -> None:
    service = ItemService(FakeItemRepository([_owned_item()]))

    result = await service.update(1, OWNER_ID, ItemUpdate(title="new"))

    assert result.title == "new"
    assert result.description == "old-desc"


async def test_update_clears_description_when_explicitly_null() -> None:
    service = ItemService(FakeItemRepository([_owned_item()]))

    result = await service.update(1, OWNER_ID, ItemUpdate(description=None))

    assert result.description is None
    assert result.title == "old"


async def test_delete_removes_the_item() -> None:
    repo = FakeItemRepository([_owned_item()])
    service = ItemService(repo)

    await service.delete(1, OWNER_ID)

    assert [item.id for item in repo.deleted] == [1]
    assert await repo.count_for_owner(OWNER_ID) == 0


async def test_list_for_owner_reports_the_unpaginated_total() -> None:
    items = []
    for index in range(3):
        item = Item(title=f"item-{index}", owner_id=OWNER_ID)
        item.id = index + 1
        items.append(item)
    service = ItemService(FakeItemRepository(items))

    page, total = await service.list_for_owner(OWNER_ID, limit=2, offset=0)

    assert [item.id for item in page] == [1, 2]
    assert total == 3
