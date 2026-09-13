from datetime import UTC, datetime, timedelta

from app.core.error_codes import ErrorCode
from app.core.exceptions import AuthError
from app.core.security import (
    hash_password,
    hash_single_use_token,
    new_single_use_token,
)
from app.models.single_use_token import SingleUseToken, TokenPurpose
from app.schemas.user import normalize_email
from app.services.protocols import (
    AccountMailerProtocol,
    RefreshTokenRepositoryProtocol,
    SingleUseTokenRepositoryProtocol,
    UserRepositoryProtocol,
)

INVALID_TOKEN = "This reset link is no longer valid"


class PasswordResetService:
    def __init__(
        self,
        users: UserRepositoryProtocol,
        tokens: SingleUseTokenRepositoryProtocol,
        sessions: RefreshTokenRepositoryProtocol,
        mailer: AccountMailerProtocol,
        *,
        lifetime: timedelta,
    ) -> None:
        self._users = users
        self._tokens = tokens
        self._sessions = sessions
        self._mailer = mailer
        self._lifetime = lifetime

    async def request(self, email: str) -> None:
        user = await self._users.get_by_email(normalize_email(email))
        if user is None:
            return

        now = datetime.now(UTC)
        await self._tokens.revoke_all_for(user.id, TokenPurpose.PASSWORD_RESET, now)
        token = new_single_use_token()
        expires_at = now + self._lifetime
        await self._tokens.create(
            SingleUseToken(
                token_hash=hash_single_use_token(token),
                user_id=user.id,
                purpose=TokenPurpose.PASSWORD_RESET,
                expires_at=expires_at,
            )
        )
        await self._mailer.send_password_reset(user, token, expires_at)

    async def confirm(self, token: str, new_password: str) -> None:
        now = datetime.now(UTC)
        stored = await self._tokens.get_active(
            hash_single_use_token(token), TokenPurpose.PASSWORD_RESET, now
        )
        if stored is None:
            raise AuthError(INVALID_TOKEN, code=ErrorCode.AUTH_INVALID_TOKEN)

        user = await self._users.get(stored.user_id)
        if user is None:
            raise AuthError(INVALID_TOKEN, code=ErrorCode.AUTH_INVALID_TOKEN)

        user.hashed_password = hash_password(new_password)
        await self._users.save(user)
        await self._tokens.mark_used(stored, now)
        await self._tokens.revoke_all_for(user.id, TokenPurpose.PASSWORD_RESET, now)
        await self._sessions.revoke_all_for_user(user.id, now)
