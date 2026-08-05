from unittest.mock import AsyncMock

import pytest

from app.core.exceptions import NotFoundError
from app.schemas.item import ItemUpdate
from app.services.item_service import ItemService


async def test_get_for_owner_missing_raises() -> None:
    repo = AsyncMock()
    repo.get_for_owner.return_value = None
    service = ItemService(repo)
    with pytest.raises(NotFoundError):
        await service.get_for_owner(1, 1)


async def test_update_applies_only_provided_fields() -> None:
    repo = AsyncMock()

    class FakeItem:
        title = "old"
        description = "old-desc"

    repo.get_for_owner.return_value = FakeItem()
    service = ItemService(repo)
    result = await service.update(1, 1, ItemUpdate(title="new"))
    assert result.title == "new"
    assert result.description == "old-desc"


async def test_update_clears_description_when_explicitly_null() -> None:
    repo = AsyncMock()

    class FakeItem:
        title = "old"
        description = "old-desc"

    repo.get_for_owner.return_value = FakeItem()
    service = ItemService(repo)
    result = await service.update(1, 1, ItemUpdate(description=None))
    assert result.description is None
    assert result.title == "old"
