from collections.abc import Sequence

from app.models.item import Item
from app.models.user import User


class FakeUserRepository:
    def __init__(self, users: Sequence[User] = ()) -> None:
        self._users: list[User] = list(users)
        self.created: list[User] = []
        self.deactivated: list[User] = []

    async def get_by_email(self, email: str) -> User | None:
        return next((user for user in self._users if user.email == email), None)

    async def get(self, user_id: int) -> User | None:
        return next((user for user in self._users if user.id == user_id), None)

    async def create(self, user: User) -> User:
        user.id = len(self._users) + 1
        self._users.append(user)
        self.created.append(user)
        return user

    async def list_all(self, limit: int, offset: int) -> Sequence[User]:
        return self._users[offset : offset + limit]

    async def count_all(self) -> int:
        return len(self._users)

    async def soft_delete(self, user: User) -> None:
        user.mark_deleted()
        self.deactivated.append(user)


class FakeItemRepository:
    def __init__(self, items: Sequence[Item] = ()) -> None:
        self._items: list[Item] = list(items)
        self.deleted: list[Item] = []

    async def list_for_owner(
        self, owner_id: int, limit: int, offset: int
    ) -> Sequence[Item]:
        owned = [item for item in self._items if item.owner_id == owner_id]
        return owned[offset : offset + limit]

    async def count_for_owner(self, owner_id: int) -> int:
        return sum(1 for item in self._items if item.owner_id == owner_id)

    async def get_for_owner(self, item_id: int, owner_id: int) -> Item | None:
        return next(
            (
                item
                for item in self._items
                if item.id == item_id and item.owner_id == owner_id
            ),
            None,
        )

    async def create(self, item: Item) -> Item:
        item.id = len(self._items) + 1
        self._items.append(item)
        return item

    async def soft_delete(self, item: Item) -> None:
        item.mark_deleted()
        self._items.remove(item)
        self.deleted.append(item)

    async def soft_delete_for_owner(self, owner_id: int) -> None:
        for item in [i for i in self._items if i.owner_id == owner_id]:
            await self.soft_delete(item)
