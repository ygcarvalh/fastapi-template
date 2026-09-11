from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import (
    CurrentUser,
    PreferencesServiceDep,
    RequireAuth,
    UserServiceDep,
    require_role,
)
from app.core.config import get_settings
from app.core.http.rate_limit import limiter
from app.models.user import UserRole
from app.schemas.error import AUTHENTICATED_ERROR_RESPONSES
from app.schemas.pagination import Page, PageParams
from app.schemas.preferences import PreferencesRead, PreferencesUpdate
from app.schemas.user import (
    AccountDeactivate,
    UserCreate,
    UserRead,
    UserRoleUpdate,
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


@private_router.patch("/me")
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


@private_router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_me(
    data: AccountDeactivate, current_user: CurrentUser, service: UserServiceDep
) -> None:
    await service.deactivate(current_user, data.password)


@private_router.get("", dependencies=[require_role(UserRole.ADMIN)])
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


@private_router.get("/{user_id}", dependencies=[require_role(UserRole.ADMIN)])
async def read_user(user_id: int, service: UserServiceDep) -> UserRead:
    return UserRead.model_validate(await service.get(user_id))


@private_router.patch("/{user_id}/role", dependencies=[require_role(UserRole.ADMIN)])
async def update_user_role(
    user_id: int,
    data: UserRoleUpdate,
    current_user: CurrentUser,
    service: UserServiceDep,
) -> UserRead:
    user = await service.set_role(current_user, user_id, data.role)
    return UserRead.model_validate(user)
