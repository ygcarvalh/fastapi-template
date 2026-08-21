from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_preferences import UserPreferences


class PreferencesRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_for_user(self, user_id: int) -> UserPreferences | None:
        result = await self._session.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(self, preferences: UserPreferences) -> UserPreferences:
        self._session.add(preferences)
        await self._session.flush()
        await self._session.refresh(preferences)
        return preferences

    async def save(self, preferences: UserPreferences) -> UserPreferences:
        await self._session.flush()
        await self._session.refresh(preferences)
        return preferences
