from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import BASE_ROLES
from app.models.role import Permission, Role, RolePermission


async def seed_roles(session: AsyncSession) -> None:
    permissions: dict[tuple[str, str], Permission] = {}
    for grants in BASE_ROLES.values():
        for resource, action, _scope in grants:
            if (resource, action) not in permissions:
                permissions[(resource, action)] = Permission(
                    resource=resource, action=action
                )
    session.add_all(permissions.values())

    for name, grants in BASE_ROLES.items():
        role = Role(name=name)
        role.grants = [
            RolePermission(permission=permissions[(resource, action)], scope=scope)
            for resource, action, scope in grants
        ]
        session.add(role)

    await session.flush()
