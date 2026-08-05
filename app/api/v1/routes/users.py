from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import CurrentUser, RequireAuth, UserServiceDep, require_role
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.models.user import UserRole
from app.schemas.pagination import Page, PageParams
from app.schemas.user import UserCreate, UserRead

public_router = APIRouter(prefix="/users", tags=["users"])
private_router = APIRouter(prefix="/users", tags=["users"], dependencies=[RequireAuth])


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
