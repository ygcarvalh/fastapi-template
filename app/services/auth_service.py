from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import NamedTuple

from app.core.audit.events import IMPERSONATION, audit_event
from app.core.audit.policy import AuditAction
from app.core.authorization import may_impersonate
from app.core.config import get_settings
from app.core.exceptions import AuthError, ForbiddenError
from app.core.security import (
    INVALID_CREDENTIALS,
    create_access_token,
    create_impersonation_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.user import PasswordChange, normalize_email
from app.services.protocols import (
    AuditLogRepositoryProtocol,
    RefreshTokenRepositoryProtocol,
    UserRepositoryProtocol,
)

SECONDS_PER_MINUTE = 60


class TokenPair(NamedTuple):
    access_token: str
    refresh_token: str


class ImpersonationGrant(NamedTuple):
    access_token: str
    expires_in: int


@lru_cache(maxsize=1)
def _hash_for_absent_user() -> str:
    return hash_password("absent-user-constant-time-placeholder")


class AuthService:
    def __init__(
        self,
        users: UserRepositoryProtocol,
        tokens: RefreshTokenRepositoryProtocol,
        audit: AuditLogRepositoryProtocol,
    ) -> None:
        self._users = users
        self._tokens = tokens
        self._audit = audit

    async def authenticate(self, email: str, password: str) -> TokenPair:
        user = await self._users.get_by_email(normalize_email(email))
        hashed = user.hashed_password if user is not None else _hash_for_absent_user()
        password_matches = verify_password(password, hashed)
        if user is None or not password_matches:
            raise AuthError("Incorrect email or password")
        return await self._issue(user)

    # The refresh token is not rotated. The frontend refreshes from two places,
    # so a rotation race would sign readers out at random; the stored row is
    # what makes the token revocable, which is the property that matters.
    async def refresh(self, refresh_token: str) -> TokenPair:
        subject = decode_refresh_token(refresh_token)
        try:
            user_id = int(subject)
        except ValueError as exc:
            raise AuthError(INVALID_CREDENTIALS) from exc

        stored = await self._tokens.get_active(
            hash_refresh_token(refresh_token), datetime.now(UTC)
        )
        if stored is None or stored.user_id != user_id:
            raise AuthError(INVALID_CREDENTIALS)

        user = await self._users.get(user_id)
        if user is None:
            raise AuthError(INVALID_CREDENTIALS)
        return TokenPair(create_access_token(str(user.id)), refresh_token)

    # No refresh token comes with it, and stopping does not revoke it: the
    # token is stateless, so the short lifetime is what bounds the exposure.
    async def impersonate(self, actor: User, target: User) -> ImpersonationGrant:
        if target.id == actor.id:
            raise ForbiddenError("An account cannot impersonate itself")
        if not may_impersonate(actor, target):
            raise ForbiddenError("Insufficient permissions")

        minutes = get_settings().impersonation_token_expire_minutes
        await self._record(AuditAction.IMPERSONATE_START, target, {"old": None})
        return ImpersonationGrant(
            create_impersonation_token(str(target.id), str(actor.id)),
            minutes * SECONDS_PER_MINUTE,
        )

    async def stop_impersonating(self, target: User) -> None:
        await self._record(AuditAction.IMPERSONATE_STOP, target, {"new": None})

    async def _record(
        self, action: AuditAction, target: User, side: dict[str, object]
    ) -> None:
        await self._audit.create(
            audit_event(
                IMPERSONATION,
                action,
                row_pk=str(target.id),
                changes={"target": {"old": None, "new": target.id, **side}},
            )
        )

    async def logout(self, refresh_token: str) -> None:
        await self._tokens.revoke(hash_refresh_token(refresh_token), datetime.now(UTC))

    async def revoke_sessions(self, user: User) -> int:
        return await self._tokens.revoke_all_for_user(user.id, datetime.now(UTC))

    # A valid access token is not enough, or a leaked one would be a takeover.
    # Every refresh token goes with the old password; access tokens already
    # minted keep working, since nothing is stored to compare them against.
    async def change_password(self, user: User, data: PasswordChange) -> None:
        if not verify_password(data.current_password, user.hashed_password):
            raise ForbiddenError("Current password is incorrect")
        user.hashed_password = hash_password(data.new_password)
        await self._users.save(user)
        await self.revoke_sessions(user)

    async def _issue(self, user: User) -> TokenPair:
        settings = get_settings()
        pair = TokenPair(
            create_access_token(str(user.id)), create_refresh_token(str(user.id))
        )
        await self._tokens.create(
            RefreshToken(
                token_hash=hash_refresh_token(pair.refresh_token),
                user_id=user.id,
                expires_at=datetime.now(UTC)
                + timedelta(days=settings.refresh_token_expire_days),
            )
        )
        return pair
