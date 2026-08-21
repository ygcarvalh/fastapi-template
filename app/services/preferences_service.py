from app.models.user import User
from app.models.user_preferences import (
    DEFAULT_LOCALE,
    DEFAULT_THEME,
    UserPreferences,
)
from app.schemas.preferences import PreferencesUpdate
from app.services.protocols import PreferencesRepositoryProtocol


class PreferencesService:
    def __init__(self, repo: PreferencesRepositoryProtocol) -> None:
        self._repo = repo

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
            show_request_id=True,
        )

    async def update(self, user: User, data: PreferencesUpdate) -> UserPreferences:
        stored = await self._repo.get_for_user(user.id)
        fields = data.model_dump(exclude_unset=True, exclude_none=True)
        if stored is None:
            return await self._repo.create(UserPreferences(user_id=user.id, **fields))
        for name, value in fields.items():
            setattr(stored, name, value)
        return await self._repo.save(stored)
