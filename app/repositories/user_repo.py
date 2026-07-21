from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    async def create(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user
