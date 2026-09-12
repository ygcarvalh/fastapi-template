from fastapi import APIRouter, status

from app.api.deps import RequireAuth, RoleServiceDep, require_permission
from app.core.authorization import CREATE, DELETE, READ, ROLES, UPDATE
from app.schemas.error import AUTHENTICATED_ERROR_RESPONSES
from app.schemas.role import PermissionRead, RoleRead, RoleWrite, to_role_read

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
