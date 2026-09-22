from collections.abc import Sequence

from sqlalchemy import select

from app.models.role import Permission, Role
from app.repositories.base import BaseRepository, CrudRepository


class RoleRepository(CrudRepository[Role]):
    _model = Role

    async def get_by_name(self, name: str) -> Role | None:
        return await self._one_or_none(select(Role).where(Role.name == name))

    async def list_all(self) -> Sequence[Role]:
        return await self._all(select(Role).order_by(Role.name))


class PermissionRepository(BaseRepository):
    async def get(self, resource: str, action: str) -> Permission | None:
        return await self._one_or_none(
            select(Permission).where(
                Permission.resource == resource, Permission.action == action
            )
        )

    async def list_all(self) -> Sequence[Permission]:
        return await self._all(
            select(Permission).order_by(Permission.resource, Permission.action)
        )
