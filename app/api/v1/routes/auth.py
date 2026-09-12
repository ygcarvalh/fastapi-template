from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from app.api.deps import (
    AuthServiceDep,
    CurrentActor,
    CurrentUser,
    ForbidImpersonation,
    RequireAuth,
    UserServiceDep,
    require_permission,
)
from app.core.authorization import IMPERSONATE, USERS
from app.core.config import get_settings
from app.core.http.rate_limit import limiter
from app.models.role import Scope
from app.schemas.auth import ImpersonationToken, RefreshRequest, Token
from app.schemas.error import AUTHENTICATED_ERROR_RESPONSES
from app.schemas.user import PasswordChange, UserRead
from app.services.auth_service import TokenPair

public_router = APIRouter(prefix="/auth", tags=["auth"])
private_router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    dependencies=[RequireAuth],
    responses=AUTHENTICATED_ERROR_RESPONSES,
)


def _as_token(pair: TokenPair) -> Token:
    return Token(access_token=pair.access_token, refresh_token=pair.refresh_token)


@public_router.post("/login")
@limiter.limit(lambda: get_settings().login_rate_limit)
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    service: AuthServiceDep,
) -> Token:
    pair = await service.authenticate(form_data.username, form_data.password)
    return _as_token(pair)


@public_router.post("/refresh")
@limiter.limit(lambda: get_settings().login_rate_limit)
async def refresh(
    request: Request,
    data: RefreshRequest,
    service: AuthServiceDep,
) -> Token:
    pair = await service.refresh(data.refresh_token)
    return _as_token(pair)


# Public because a client whose access token has already expired still has to be
# able to retire its refresh token, and the token it sends is the credential.
# Throttled because it is an unauthenticated write.
@public_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(lambda: get_settings().login_rate_limit)
async def logout(
    request: Request, data: RefreshRequest, service: AuthServiceDep
) -> None:
    await service.logout(data.refresh_token)


# Declared before the parameterised route, or "stop" arrives as a user id.
@private_router.post("/impersonate/stop", status_code=status.HTTP_204_NO_CONTENT)
async def stop_impersonating(actor: CurrentActor, service: AuthServiceDep) -> None:
    if actor.impersonator is not None:
        await service.stop_impersonating(actor.user)


@private_router.post("/impersonate/{user_id}")
@limiter.limit(lambda: get_settings().login_rate_limit)
async def impersonate(
    request: Request,
    user_id: int,
    current_user: CurrentUser,
    users: UserServiceDep,
    service: AuthServiceDep,
    scope: Annotated[Scope, require_permission(USERS, IMPERSONATE)],
) -> ImpersonationToken:
    target = await users.get(user_id)
    grant = await service.impersonate(current_user, target)
    return ImpersonationToken(
        access_token=grant.access_token,
        expires_in=grant.expires_in,
        user=UserRead.model_validate(target),
        impersonator=UserRead.model_validate(current_user),
    )


@private_router.post(
    "/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[ForbidImpersonation],
)
@limiter.limit(lambda: get_settings().login_rate_limit)
async def change_password(
    request: Request,
    data: PasswordChange,
    current_user: CurrentUser,
    service: AuthServiceDep,
) -> None:
    await service.change_password(current_user, data)
