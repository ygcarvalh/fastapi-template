from collections.abc import Sequence

from app.models.item import Item
from app.models.user import User


class FakeUserRepository:
    def __init__(self, users: Sequence[User] = ()) -> None:
        self._users: list[User] = list(users)
        self.created: list[User] = []

    async def get_by_email(self, email: str) -> User | None:
        return next((user for user in self._users if user.email == email), None)

    async def get(self, user_id: int) -> User | None:
        return next((user for user in self._users if user.id == user_id), None)

    async def create(self, user: User) -> User:
        user.id = len(self._users) + 1
        self._users.append(user)
        self.created.append(user)
        return user


class FakeItemRepository:
    def __init__(self, items: Sequence[Item] = ()) -> None:
        self._items: list[Item] = list(items)
        self.deleted: list[Item] = []

    async def list_for_owner(self, owner_id: int) -> Sequence[Item]:
        return [item for item in self._items if item.owner_id == owner_id]

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

    async def delete(self, item: Item) -> None:
        self._items.remove(item)
        self.deleted.append(item)
