from app.core.error_codes import ErrorCode
from app.core.features import available_features
from app.models.user import User
from app.models.user_preferences import (
    DEFAULT_LOCALE,
    DEFAULT_THEME,
    DEFAULT_TIMEZONE,
    UserPreferences,
)
from app.schemas.preferences import (
    AccountFeaturesRead,
    AccountFeaturesUpdate,
    PreferencesUpdate,
)
from app.services.protocols import (
    PreferencesRepositoryProtocol,
    UserRepositoryProtocol,
)
from app.services.support import or_not_found

# Fields where null is an answer rather than an omission.
NULLABLE_FIELDS = frozenset({"features"})


class PreferencesService:
    def __init__(
        self, repo: PreferencesRepositoryProtocol, users: UserRepositoryProtocol
    ) -> None:
        self._repo = repo
        self._users = users

    async def _user(self, user_id: int) -> User:
        return or_not_found(
            await self._users.get(user_id), "User not found", ErrorCode.USER_NOT_FOUND
        )

    async def features_for(self, user_id: int) -> AccountFeaturesRead:
        user = await self._user(user_id)
        stored = await self.get(user)
        return AccountFeaturesRead(
            features=stored.features, available=available_features()
        )

    async def update_features_for(
        self, user_id: int, data: AccountFeaturesUpdate
    ) -> AccountFeaturesRead:
        user = await self._user(user_id)
        stored = await self.update(user, PreferencesUpdate(features=data.features))
        return AccountFeaturesRead(
            features=stored.features, available=available_features()
        )

    # A row is written on the first change rather than at registration, so an
    # account that never opens settings costs nothing.
    async def get(self, user: User) -> UserPreferences:
        stored = await self._repo.get_for_user(user.id)
        if stored is not None:
            return stored
        return UserPreferences(
            user_id=user.id,
            locale=DEFAULT_LOCALE,
            theme=DEFAULT_THEME,
            timezone=DEFAULT_TIMEZONE,
            show_request_id=True,
        )

    async def update(self, user: User, data: PreferencesUpdate) -> UserPreferences:
        stored = await self._repo.get_for_user(user.id)
        sent = data.model_dump(exclude_unset=True)
        fields = {
            name: value
            for name, value in sent.items()
            if value is not None or name in NULLABLE_FIELDS
        }
        if stored is None:
            return await self._repo.create(UserPreferences(user_id=user.id, **fields))
        for name, value in fields.items():
            setattr(stored, name, value)
        return await self._repo.save(stored)
