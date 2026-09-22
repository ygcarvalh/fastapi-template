from collections.abc import Sequence

from sqlalchemy import func, select

from app.models.role import user_roles
from app.models.user import User
from app.repositories.base import CrudRepository, SoftDeleteRepository


class UserRepository(CrudRepository[User], SoftDeleteRepository[User]):
    _model = User

    async def get_by_email(self, email: str) -> User | None:
        return await self._one_or_none(
            select(User).where(User.email == email, User.is_active())
        )

    async def get(self, user_id: int) -> User | None:
        return await self._one_or_none(
            select(User).where(User.id == user_id, User.is_active())
        )

    async def list_all(self, limit: int, offset: int) -> Sequence[User]:
        return await self._all(
            select(User)
            .where(User.is_active())
            .order_by(User.id)
            .limit(limit)
            .offset(offset)
        )

    async def count_all(self) -> int:
        return await self._one(
            select(func.count()).select_from(User).where(User.is_active())
        )

    async def count_for_role(self, role_id: int) -> int:
        return await self._one(
            select(func.count())
            .select_from(User)
            .join(user_roles, user_roles.c.user_id == User.id)
            .where(user_roles.c.role_id == role_id, User.is_active())
        )

    async def list_for_role(self, role_id: int) -> Sequence[User]:
        return await self._all(
            select(User)
            .join(user_roles, user_roles.c.user_id == User.id)
            .where(user_roles.c.role_id == role_id, User.is_active())
            .order_by(User.id)
        )

    async def exists_any(self) -> bool:
        return await self._one(select(select(User.id).exists()))
