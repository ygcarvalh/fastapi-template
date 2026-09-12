from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import (
    CurrentUser,
    ForbidImpersonation,
    PreferencesServiceDep,
    RequireAuth,
    RoleServiceDep,
    UserServiceDep,
    require_permission,
)
from app.core.authorization import (
    FEATURE_FLAGS,
    READ,
    UPDATE,
    USERS,
    granted,
    is_superuser,
)
from app.core.config import get_settings
from app.core.features import available_features
from app.core.http.rate_limit import limiter
from app.models.role import Scope
from app.schemas.error import AUTHENTICATED_ERROR_RESPONSES
from app.schemas.pagination import Page, PageParams
from app.schemas.preferences import (
    AccountFeaturesRead,
    AccountFeaturesUpdate,
    PreferencesRead,
    PreferencesUpdate,
)
from app.schemas.user import (
    AccountDeactivate,
    GrantRead,
    RoleAssignment,
    UserCreate,
    UserRead,
    UserUpdate,
)

public_router = APIRouter(prefix="/users", tags=["users"])
private_router = APIRouter(
    prefix="/users",
    tags=["users"],
    dependencies=[RequireAuth],
    responses=AUTHENTICATED_ERROR_RESPONSES,
)


@public_router.post("", status_code=status.HTTP_201_CREATED)
@limiter.limit(lambda: get_settings().register_rate_limit)
async def register_user(
    request: Request, data: UserCreate, service: UserServiceDep
) -> UserRead:
    user = await service.register(data)
    return UserRead.model_validate(user)


@private_router.get("/me")
async def read_me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@private_router.patch("/me", dependencies=[ForbidImpersonation])
async def update_me(
    data: UserUpdate, current_user: CurrentUser, service: UserServiceDep
) -> UserRead:
    user = await service.update(current_user, data)
    return UserRead.model_validate(user)


@private_router.get("/me/preferences")
async def read_my_preferences(
    current_user: CurrentUser, service: PreferencesServiceDep
) -> PreferencesRead:
    return PreferencesRead.model_validate(await service.get(current_user))


@private_router.patch("/me/preferences")
async def update_my_preferences(
    data: PreferencesUpdate, current_user: CurrentUser, service: PreferencesServiceDep
) -> PreferencesRead:
    return PreferencesRead.model_validate(await service.update(current_user, data))


@private_router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[ForbidImpersonation],
)
async def deactivate_me(
    data: AccountDeactivate, current_user: CurrentUser, service: UserServiceDep
) -> None:
    await service.deactivate(current_user, data.password)


@private_router.get("/me/permissions")
async def read_my_permissions(
    current_user: CurrentUser, roles: RoleServiceDep
) -> list[GrantRead]:
    if is_superuser(current_user):
        return [
            GrantRead(
                resource=permission.resource,
                action=permission.action,
                scope=Scope.ALL,
            )
            for permission in await roles.list_permissions()
        ]
    return [
        GrantRead(resource=resource, action=action, scope=scope)
        for resource, action, scope in granted(current_user)
    ]


@private_router.get("", dependencies=[require_permission(USERS, READ)])
async def list_users(
    service: UserServiceDep,
    page: Annotated[PageParams, Query()],
) -> Page[UserRead]:
    users, total = await service.list_all(page.limit, page.offset)
    return Page(
        items=[UserRead.model_validate(user) for user in users],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@private_router.get("/{user_id}", dependencies=[require_permission(USERS, READ)])
async def read_user(user_id: int, service: UserServiceDep) -> UserRead:
    return UserRead.model_validate(await service.get(user_id))


@private_router.get(
    "/{user_id}/features",
    dependencies=[
        require_permission(USERS, READ),
        require_permission(FEATURE_FLAGS, READ),
    ],
)
async def read_user_features(
    user_id: int, users: UserServiceDep, preferences: PreferencesServiceDep
) -> AccountFeaturesRead:
    stored = await preferences.get(await users.get(user_id))
    return AccountFeaturesRead(features=stored.features, available=available_features())


@private_router.put(
    "/{user_id}/features", dependencies=[require_permission(FEATURE_FLAGS, UPDATE)]
)
async def update_user_features(
    user_id: int,
    data: AccountFeaturesUpdate,
    users: UserServiceDep,
    preferences: PreferencesServiceDep,
) -> AccountFeaturesRead:
    target = await users.get(user_id)
    stored = await preferences.update(target, PreferencesUpdate(features=data.features))
    return AccountFeaturesRead(features=stored.features, available=available_features())


@private_router.post(
    "/{user_id}/roles", dependencies=[require_permission(USERS, UPDATE)]
)
async def add_user_role(
    user_id: int, data: RoleAssignment, service: UserServiceDep
) -> UserRead:
    return UserRead.model_validate(await service.add_role(user_id, data.role))


@private_router.delete(
    "/{user_id}/roles/{role_name}", dependencies=[require_permission(USERS, UPDATE)]
)
async def remove_user_role(
    user_id: int,
    role_name: str,
    current_user: CurrentUser,
    service: UserServiceDep,
) -> UserRead:
    user = await service.remove_role(current_user, user_id, role_name)
    return UserRead.model_validate(user)
