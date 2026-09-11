from collections.abc import Sequence
from datetime import datetime

from app.models.item import Item
from app.models.refresh_token import RefreshToken
from app.models.request_log import RequestLog
from app.models.user import User
from app.models.user_preferences import UserPreferences
from app.schemas.request_log import RequestLogQuery, decode_cursor, outcome_for


class FakeUserRepository:
    def __init__(self, users: Sequence[User] = ()) -> None:
        self._users: list[User] = list(users)
        self.created: list[User] = []
        self.saved: list[User] = []
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

    async def save(self, user: User) -> User:
        self.saved.append(user)
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
        self.saved: list[Item] = []

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

    async def save(self, item: Item) -> Item:
        self.saved.append(item)
        return item

    async def soft_delete(self, item: Item) -> None:
        item.mark_deleted()
        self._items.remove(item)
        self.deleted.append(item)

    async def soft_delete_for_owner(self, owner_id: int) -> None:
        for item in [i for i in self._items if i.owner_id == owner_id]:
            await self.soft_delete(item)


class FakeRequestLogRepository:
    def __init__(self, entries: Sequence[RequestLog] = ()) -> None:
        self._entries: list[RequestLog] = list(entries)
        # The ordering key is (created_at, id), so a row without an id cannot be
        # placed. The database assigns one; here the fixture order does.
        for position, entry in enumerate(self._entries, start=1):
            if entry.id is None:
                entry.id = position
        self.pruned: list[datetime] = []

    def _matching(self, query: RequestLogQuery) -> list[RequestLog]:
        entries = self._entries
        if query.user_id is not None:
            entries = [entry for entry in entries if entry.user_id == query.user_id]
        if query.outcome is not None:
            entries = [
                entry
                for entry in entries
                if outcome_for(entry.status_code) == query.outcome
            ]
        if query.path:
            entries = [entry for entry in entries if entry.path.startswith(query.path)]
        if query.request_id:
            entries = [
                entry for entry in entries if entry.request_id == query.request_id
            ]
        if query.since is not None:
            entries = [entry for entry in entries if entry.created_at >= query.since]
        if query.until is not None:
            entries = [entry for entry in entries if entry.created_at <= query.until]
        if query.cursor is not None:
            moment, entry_id = decode_cursor(query.cursor)
            entries = [
                entry
                for entry in entries
                if (entry.created_at, entry.id) < (moment, entry_id)
            ]
        return sorted(
            entries, key=lambda entry: (entry.created_at, entry.id), reverse=True
        )

    async def create(self, entry: RequestLog) -> RequestLog:
        entry.id = len(self._entries) + 1
        self._entries.append(entry)
        return entry

    async def list_page(self, query: RequestLogQuery) -> Sequence[RequestLog]:
        return self._matching(query)[: query.limit + 1]

    async def delete_batch_created_before(
        self, cutoff: datetime, batch_size: int
    ) -> int:
        doomed = [entry for entry in self._entries if entry.created_at < cutoff][
            :batch_size
        ]
        self._entries = [entry for entry in self._entries if entry not in doomed]
        self.pruned.append(cutoff)
        return len(doomed)


class FakePreferencesRepository:
    def __init__(self, stored: UserPreferences | None = None) -> None:
        self._stored = stored
        self.created: list[UserPreferences] = []
        self.saved: list[UserPreferences] = []

    async def get_for_user(self, user_id: int) -> UserPreferences | None:
        if self._stored is not None and self._stored.user_id == user_id:
            return self._stored
        return None

    async def create(self, preferences: UserPreferences) -> UserPreferences:
        self._stored = preferences
        self.created.append(preferences)
        return preferences

    async def save(self, preferences: UserPreferences) -> UserPreferences:
        self.saved.append(preferences)
        return preferences


class FakeRefreshTokenRepository:
    def __init__(self, tokens: Sequence[RefreshToken] = ()) -> None:
        self._tokens: list[RefreshToken] = list(tokens)

    async def create(self, token: RefreshToken) -> RefreshToken:
        token.id = len(self._tokens) + 1
        self._tokens.append(token)
        return token

    async def get_active(self, token_hash: str, now: datetime) -> RefreshToken | None:
        return next(
            (
                token
                for token in self._tokens
                if token.token_hash == token_hash
                and token.revoked_at is None
                and token.expires_at > now
            ),
            None,
        )

    async def revoke(self, token_hash: str, now: datetime) -> int:
        revoked = 0
        for token in self._tokens:
            if token.token_hash == token_hash and token.revoked_at is None:
                token.revoked_at = now
                revoked += 1
        return revoked

    async def revoke_all_for_user(self, user_id: int, now: datetime) -> int:
        revoked = 0
        for token in self._tokens:
            if token.user_id == user_id and token.revoked_at is None:
                token.revoked_at = now
                revoked += 1
        return revoked

    async def delete_expired(self, now: datetime) -> int:
        expired = [token for token in self._tokens if token.expires_at <= now]
        self._tokens = [token for token in self._tokens if token not in expired]
        return len(expired)
