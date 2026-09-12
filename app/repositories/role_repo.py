from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Permission, Role


class RoleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, role_id: int) -> Role | None:
        result = await self._session.execute(select(Role).where(Role.id == role_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Role | None:
        result = await self._session.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[Role]:
        result = await self._session.execute(select(Role).order_by(Role.name))
        return result.scalars().all()

    async def create(self, role: Role) -> Role:
        self._session.add(role)
        await self._session.flush()
        await self._session.refresh(role)
        return role

    async def save(self, role: Role) -> Role:
        await self._session.flush()
        await self._session.refresh(role)
        return role

    async def delete(self, role: Role) -> None:
        await self._session.delete(role)
        await self._session.flush()


class PermissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, resource: str, action: str) -> Permission | None:
        result = await self._session.execute(
            select(Permission).where(
                Permission.resource == resource, Permission.action == action
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[Permission]:
        result = await self._session.execute(
            select(Permission).order_by(Permission.resource, Permission.action)
        )
        return result.scalars().all()
