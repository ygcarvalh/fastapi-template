from sqlalchemy import select

from app.models.user_preferences import UserPreferences
from app.repositories.base import BaseRepository


class PreferencesRepository(BaseRepository):
    async def get_for_user(self, user_id: int) -> UserPreferences | None:
        return await self._one_or_none(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )

    async def create(self, preferences: UserPreferences) -> UserPreferences:
        return await self._insert_refreshed(preferences)

    async def save(self, preferences: UserPreferences) -> UserPreferences:
        return await self._save(preferences)
