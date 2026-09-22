from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Annotated

import structlog
from fastapi import Depends, Request, params
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit.context import bind_actor
from app.core.authorization import (
    BLOCKED_WHILE_IMPERSONATING,
    may_impersonate,
    scope_for,
)
from app.core.config import get_settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import ForbiddenError, NotFoundError
from app.core.mail.sender import LoggingMailSender, MailSender, SmtpMailSender
from app.core.security import decode_access_token, invalid_credentials
from app.core.storage.backend import Storage
from app.core.storage.local import LocalStorage
from app.db.session import get_session
from app.models.role import Scope
from app.models.user import User
from app.repositories.attachment_repo import AttachmentRepository
from app.repositories.audit_log_repo import AuditLogRepository
from app.repositories.item_repo import ItemRepository
from app.repositories.preferences_repo import PreferencesRepository
from app.repositories.refresh_token_repo import RefreshTokenRepository
from app.repositories.request_log_repo import RequestLogRepository
from app.repositories.role_repo import PermissionRepository, RoleRepository
from app.repositories.single_use_token_repo import SingleUseTokenRepository
from app.repositories.user_repo import UserRepository
from app.services.account_mailer import AccountMailer
from app.services.attachment_service import AttachmentService
from app.services.audit_log_service import AuditLogService
from app.services.auth_service import AuthService
from app.services.email_verification_service import EmailVerificationService
from app.services.item_service import ItemService
from app.services.password_reset_service import PasswordResetService
from app.services.preferences_service import PreferencesService
from app.services.request_log_service import RequestLogService
from app.services.role_service import RoleService
from app.services.user_service import UserService

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@lru_cache(maxsize=1)
def get_mail_sender() -> MailSender:
    settings = get_settings()
    if settings.mail_backend == "smtp":
        return SmtpMailSender(
            sender=settings.mail_from,
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password.get_secret_value()
            if settings.smtp_password is not None
            else None,
            use_starttls=settings.smtp_starttls,
        )
    return LoggingMailSender(settings.mail_from)


def get_account_mailer(session: SessionDep) -> AccountMailer:
    return AccountMailer(
        get_mail_sender(),
        PreferencesRepository(session),
        base_url=get_settings().app_base_url,
    )


def get_auth_service(session: SessionDep) -> AuthService:
    return AuthService(
        UserRepository(session),
        RefreshTokenRepository(session),
        AuditLogRepository(session),
        require_verified_email=get_settings().require_verified_email,
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


def get_email_verification_service(session: SessionDep) -> EmailVerificationService:
    return EmailVerificationService(
        UserRepository(session),
        SingleUseTokenRepository(session),
        get_account_mailer(session),
        lifetime=timedelta(hours=get_settings().email_verification_expire_hours),
        resend_cooldown=timedelta(seconds=get_settings().mail_resend_cooldown_seconds),
    )


EmailVerificationServiceDep = Annotated[
    EmailVerificationService, Depends(get_email_verification_service)
]


def get_password_reset_service(session: SessionDep) -> PasswordResetService:
    return PasswordResetService(
        UserRepository(session),
        SingleUseTokenRepository(session),
        RefreshTokenRepository(session),
        get_account_mailer(session),
        lifetime=timedelta(minutes=get_settings().password_reset_expire_minutes),
        resend_cooldown=timedelta(seconds=get_settings().mail_resend_cooldown_seconds),
    )


PasswordResetServiceDep = Annotated[
    PasswordResetService, Depends(get_password_reset_service)
]


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


@lru_cache(maxsize=1)
def get_storage() -> Storage:
    return LocalStorage(get_settings().storage_root)


def get_attachment_service(session: SessionDep) -> AttachmentService:
    settings = get_settings()
    return AttachmentService(
        AttachmentRepository(session),
        ItemRepository(session),
        get_storage(),
        max_bytes=settings.max_attachment_bytes,
        allowed_types=settings.attachment_type_set,
    )


AttachmentServiceDep = Annotated[AttachmentService, Depends(get_attachment_service)]


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


@dataclass(frozen=True)
class Actor:
    user: User
    impersonator: User | None

    @property
    def impersonator_id(self) -> int | None:
        return None if self.impersonator is None else self.impersonator.id


def _password_moved_after(user: User, issued_at: datetime) -> bool:
    changed = user.password_changed_at
    if changed is None:
        return False
    return changed.replace(microsecond=0) > issued_at


async def _load(service: UserService, subject: str, issued_at: datetime) -> User:
    try:
        user_id = int(subject)
    except ValueError as exc:
        raise invalid_credentials() from exc
    try:
        user = await service.get(user_id)
    except NotFoundError as exc:
        raise invalid_credentials() from exc
    if _password_moved_after(user, issued_at):
        raise invalid_credentials()
    return user


async def get_actor(
    request: Request,
    token: Annotated[str, Depends(oauth2_scheme)],
    service: UserServiceDep,
) -> Actor:
    claims = decode_access_token(token)
    user = await _load(service, claims.subject, claims.issued_at)
    impersonator = (
        None
        if claims.impersonator is None
        else await _load(service, claims.impersonator, claims.issued_at)
    )
    if impersonator is not None and not may_impersonate(impersonator, user):
        raise ForbiddenError(
            "Impersonation is no longer allowed",
            code=ErrorCode.AUTH_IMPERSONATION_REVOKED,
        )

    actor = Actor(user=user, impersonator=impersonator)
    request.state.user_id = user.id
    request.state.impersonator_id = actor.impersonator_id
    structlog.contextvars.bind_contextvars(
        user_id=user.id, impersonator_id=actor.impersonator_id
    )
    bind_actor(user.id, actor.impersonator_id)
    return actor


CurrentActor = Annotated[Actor, Depends(get_actor)]


async def get_current_user(actor: CurrentActor) -> User:
    return actor.user


CurrentUser = Annotated[User, Depends(get_current_user)]

RequireAuth = Depends(get_current_user)


async def forbid_impersonation(actor: CurrentActor) -> None:
    if actor.impersonator is not None:
        raise ForbiddenError(
            "Not allowed while impersonating",
            code=ErrorCode.AUTH_IMPERSONATION_BLOCKED,
        )


ForbidImpersonation = Depends(forbid_impersonation)


def require_permission(resource: str, action: str) -> params.Depends:
    async def guard(actor: CurrentActor) -> Scope:
        if (
            actor.impersonator is not None
            and (resource, action) in BLOCKED_WHILE_IMPERSONATING
        ):
            raise ForbiddenError(
                "Not allowed while impersonating",
                code=ErrorCode.AUTH_IMPERSONATION_BLOCKED,
            )
        scope = scope_for(actor.user, resource, action)
        if scope is None:
            raise ForbiddenError(
                "Insufficient permissions",
                code=ErrorCode.AUTH_INSUFFICIENT_PERMISSIONS,
            )
        return scope

    dependency: params.Depends = Depends(guard)
    return dependency
