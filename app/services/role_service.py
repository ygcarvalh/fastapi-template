from collections.abc import Sequence

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.role import Permission, Role, RolePermission
from app.models.user import User, UserRole
from app.schemas.role import RoleWrite
from app.services.protocols import (
    PermissionRepositoryProtocol,
    RoleRepositoryProtocol,
    UserRepositoryProtocol,
)

NAME_TAKEN = "Role name already in use"
BUILT_IN = frozenset({UserRole.USER, UserRole.ADMIN})


class RoleService:
    def __init__(
        self,
        roles: RoleRepositoryProtocol,
        permissions: PermissionRepositoryProtocol,
        users: UserRepositoryProtocol,
    ) -> None:
        self._roles = roles
        self._permissions = permissions
        self._users = users

    async def list_all(self) -> Sequence[Role]:
        return await self._roles.list_all()

    async def list_permissions(self) -> Sequence[Permission]:
        return await self._permissions.list_all()

    async def members(self, role_id: int) -> Sequence[User]:
        role = await self.get(role_id)
        return await self._users.list_for_role(role.id)

    async def get(self, role_id: int) -> Role:
        role = await self._roles.get(role_id)
        if role is None:
            raise NotFoundError("Role not found")
        return role

    async def create(self, data: RoleWrite) -> Role:
        if await self._roles.get_by_name(data.name) is not None:
            raise ConflictError(NAME_TAKEN)
        role = Role(name=data.name)
        role.grants = await self._grants(data)
        return await self._roles.create(role)

    async def update(self, role_id: int, data: RoleWrite) -> Role:
        role = await self.get(role_id)
        if role.name == UserRole.ADMIN:
            raise ForbiddenError("The administrator role always holds everything")
        taken = await self._roles.get_by_name(data.name)
        if taken is not None and taken.id != role.id:
            raise ConflictError(NAME_TAKEN)
        role.name = data.name
        role.grants = await self._grants(data)
        return await self._roles.save(role)

    async def delete(self, role_id: int) -> None:
        role = await self.get(role_id)
        if role.name in BUILT_IN:
            raise ForbiddenError("This role is part of the deployment")
        if await self._users.count_for_role(role.id) > 0:
            raise ConflictError("This role still has accounts")
        await self._roles.delete(role)

    async def _grants(self, data: RoleWrite) -> list[RolePermission]:
        grants = []
        for wanted in data.grants:
            permission = await self._permissions.get(wanted.resource, wanted.action)
            if permission is None:
                raise NotFoundError("Permission not found")
            grants.append(RolePermission(permission=permission, scope=wanted.scope))
        return grants
