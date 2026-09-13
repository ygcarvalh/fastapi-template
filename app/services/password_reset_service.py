from datetime import UTC, datetime, timedelta

from app.core.error_codes import ErrorCode
from app.core.exceptions import AuthError
from app.core.security import hash_password
from app.models.single_use_token import TokenPurpose
from app.schemas.user import normalize_email
from app.services.protocols import (
    AccountMailerProtocol,
    RefreshTokenRepositoryProtocol,
    SingleUseTokenRepositoryProtocol,
    UserRepositoryProtocol,
)
from app.services.single_use_tokens import SingleUseTokenIssuer, redeem

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
        resend_cooldown: timedelta = timedelta(0),
    ) -> None:
        self._users = users
        self._tokens = SingleUseTokenIssuer(
            tokens,
            TokenPurpose.PASSWORD_RESET,
            lifetime=lifetime,
            resend_cooldown=resend_cooldown,
        )
        self._sessions = sessions
        self._mailer = mailer

    async def request(self, email: str) -> None:
        user = await self._users.get_by_email(normalize_email(email))
        if user is None:
            return

        now = datetime.now(UTC)
        issued = await self._tokens.issue(user.id, now)
        if issued is None:
            return
        token, expires_at = issued
        await self._mailer.send_password_reset(user, token, expires_at)

    async def confirm(self, token: str, new_password: str) -> None:
        now = datetime.now(UTC)
        found = await redeem(self._tokens, self._users, token, now)
        if found is None:
            raise AuthError(INVALID_TOKEN, code=ErrorCode.AUTH_INVALID_TOKEN)

        stored, user = found
        user.hashed_password = hash_password(new_password)
        user.password_changed_at = now
        await self._users.save(user)
        await self._tokens.mark_used(stored, now)
        await self._tokens.revoke_all_for(user.id, now)
        await self._sessions.revoke_all_for_user(user.id, now)
