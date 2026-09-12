from fastapi import APIRouter, status

from app.api.deps import (
    CurrentUser,
    RequireAuth,
    RoleServiceDep,
    UserServiceDep,
    require_permission,
)
from app.core.authorization import CREATE, DELETE, READ, ROLES, UPDATE
from app.schemas.error import AUTHENTICATED_ERROR_RESPONSES
from app.schemas.role import (
    MemberAssignment,
    PermissionRead,
    RoleRead,
    RoleWrite,
    to_role_read,
)
from app.schemas.user import UserRead

private_router = APIRouter(
    prefix="/roles",
    tags=["roles"],
    dependencies=[RequireAuth],
    responses=AUTHENTICATED_ERROR_RESPONSES,
)
permissions_router = APIRouter(
    prefix="/permissions",
    tags=["roles"],
    dependencies=[RequireAuth],
    responses=AUTHENTICATED_ERROR_RESPONSES,
)


@permissions_router.get("", dependencies=[require_permission(ROLES, READ)])
async def list_permissions(service: RoleServiceDep) -> list[PermissionRead]:
    return [
        PermissionRead.model_validate(permission)
        for permission in await service.list_permissions()
    ]


@private_router.get("", dependencies=[require_permission(ROLES, READ)])
async def list_roles(service: RoleServiceDep) -> list[RoleRead]:
    return [to_role_read(role) for role in await service.list_all()]


@private_router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_permission(ROLES, CREATE)],
)
async def create_role(data: RoleWrite, service: RoleServiceDep) -> RoleRead:
    return to_role_read(await service.create(data))


@private_router.get("/{role_id}", dependencies=[require_permission(ROLES, READ)])
async def read_role(role_id: int, service: RoleServiceDep) -> RoleRead:
    return to_role_read(await service.get(role_id))


@private_router.put("/{role_id}", dependencies=[require_permission(ROLES, UPDATE)])
async def update_role(
    role_id: int, data: RoleWrite, service: RoleServiceDep
) -> RoleRead:
    return to_role_read(await service.update(role_id, data))


@private_router.delete(
    "/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[require_permission(ROLES, DELETE)],
)
async def delete_role(role_id: int, service: RoleServiceDep) -> None:
    await service.delete(role_id)


@private_router.get("/{role_id}/users", dependencies=[require_permission(ROLES, READ)])
async def list_role_members(role_id: int, service: RoleServiceDep) -> list[UserRead]:
    return [UserRead.model_validate(user) for user in await service.members(role_id)]


@private_router.post(
    "/{role_id}/users", dependencies=[require_permission(ROLES, UPDATE)]
)
async def add_role_member(
    role_id: int,
    data: MemberAssignment,
    roles: RoleServiceDep,
    users: UserServiceDep,
) -> UserRead:
    role = await roles.get(role_id)
    return UserRead.model_validate(await users.add_role(data.user_id, role.name))


@private_router.delete(
    "/{role_id}/users/{user_id}", dependencies=[require_permission(ROLES, UPDATE)]
)
async def remove_role_member(
    role_id: int,
    user_id: int,
    current_user: CurrentUser,
    roles: RoleServiceDep,
    users: UserServiceDep,
) -> UserRead:
    role = await roles.get(role_id)
    user = await users.remove_role(current_user, user_id, role.name)
    return UserRead.model_validate(user)
