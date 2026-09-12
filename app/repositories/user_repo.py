from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import user_roles
from app.models.user import User

ACTIVE = User.deleted_at.is_(None)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.email == email, ACTIVE)
        )
        return result.scalar_one_or_none()

    async def get(self, user_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.id == user_id, ACTIVE)
        )
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def save(self, user: User) -> User:
        await self._session.flush()
        await self._session.refresh(user)
        return user

    async def list_all(self, limit: int, offset: int) -> Sequence[User]:
        result = await self._session.execute(
            select(User).where(ACTIVE).order_by(User.id).limit(limit).offset(offset)
        )
        return result.scalars().all()

    async def count_all(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(User).where(ACTIVE)
        )
        return result.scalar_one()

    async def count_for_role(self, role_id: int) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(User)
            .join(user_roles, user_roles.c.user_id == User.id)
            .where(user_roles.c.role_id == role_id, ACTIVE)
        )
        return result.scalar_one()

    async def list_for_role(self, role_id: int) -> Sequence[User]:
        result = await self._session.execute(
            select(User)
            .join(user_roles, user_roles.c.user_id == User.id)
            .where(user_roles.c.role_id == role_id, ACTIVE)
            .order_by(User.id)
        )
        return result.scalars().all()

    async def exists_any(self) -> bool:
        result = await self._session.execute(select(select(User.id).exists()))
        return result.scalar_one()

    async def soft_delete(self, user: User) -> None:
        user.mark_deleted()
        await self._session.flush()
