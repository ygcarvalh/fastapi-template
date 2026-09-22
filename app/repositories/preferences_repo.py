from sqlalchemy import select

from app.models.user_preferences import UserPreferences
from app.repositories.base import CrudRepository


class PreferencesRepository(CrudRepository[UserPreferences]):
    _model = UserPreferences

    async def get_for_user(self, user_id: int) -> UserPreferences | None:
        return await self._one_or_none(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
