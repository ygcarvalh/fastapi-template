from typing import Annotated

import structlog
from fastapi import Depends, Request, params
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.context import bind_actor
from app.core.authorization import scope_for
from app.core.exceptions import AuthError, ForbiddenError, NotFoundError
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models.role import Scope
from app.models.user import User
from app.repositories.audit_log_repo import AuditLogRepository
from app.repositories.item_repo import ItemRepository
from app.repositories.preferences_repo import PreferencesRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.request_log_repo import RequestLogRepository
from app.repositories.role_repo import PermissionRepository, RoleRepository
from app.repositories.user_repo import UserRepository
from app.services.audit_log_service import AuditLogService
from app.services.auth_service import AuthService
from app.services.item_service import ItemService
from app.services.preferences_service import PreferencesService
from app.services.request_log_service import RequestLogService
from app.services.role_service import RoleService
from app.services.user_service import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_auth_service(session: SessionDep) -> AuthService:
    return AuthService(UserRepository(session), RefreshTokenRepository(session))


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_user_service(session: SessionDep) -> UserService:
    return UserService(
        UserRepository(session), ItemRepository(session), RoleRepository(session)
    )


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def get_role_service(session: SessionDep) -> RoleService:
    return RoleService(
        RoleRepository(session),
        PermissionRepository(session),
        UserRepository(session),
    )


RoleServiceDep = Annotated[RoleService, Depends(get_role_service)]


def get_item_service(session: SessionDep) -> ItemService:
    return ItemService(ItemRepository(session))


ItemServiceDep = Annotated[ItemService, Depends(get_item_service)]


def get_request_log_service(session: SessionDep) -> RequestLogService:
    return RequestLogService(RequestLogRepository(session))


RequestLogServiceDep = Annotated[RequestLogService, Depends(get_request_log_service)]


def get_audit_log_service(session: SessionDep) -> AuditLogService:
    return AuditLogService(AuditLogRepository(session))


AuditLogServiceDep = Annotated[AuditLogService, Depends(get_audit_log_service)]


def get_preferences_service(session: SessionDep) -> PreferencesService:
    return PreferencesService(PreferencesRepository(session))


PreferencesServiceDep = Annotated[PreferencesService, Depends(get_preferences_service)]


async def get_current_user(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
    service: UserServiceDep,
) -> User:
    subject = decode_access_token(token)
    try:
        user_id = int(subject)
    except ValueError as exc:
        raise AuthError("Invalid authentication credentials") from exc
    try:
        user = await service.get(user_id)
    except NotFoundError as exc:
        raise AuthError("Invalid authentication credentials") from exc
    request.state.user_id = user.id
    structlog.contextvars.bind_contextvars(user_id=user.id)
    bind_actor(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

RequireAuth = Depends(get_current_user)


def require_permission(resource: str, action: str) -> params.Depends:
    async def guard(current_user: CurrentUser) -> Scope:
        scope = scope_for(current_user, resource, action)
        if scope is None:
            raise ForbiddenError("Insufficient permissions")
        return scope

    dependency: params.Depends = Depends(guard)
    return dependency
