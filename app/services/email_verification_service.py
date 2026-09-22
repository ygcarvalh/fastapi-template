from datetime import UTC, datetime, timedelta

from app.core.error_codes import ErrorCode
from app.core.exceptions import AuthError
from app.models.single_use_token import TokenPurpose
from app.models.user import User
from app.services.protocols import (
    AccountMailerProtocol,
    SingleUseTokenRepositoryProtocol,
    UserRepositoryProtocol,
)
from app.services.single_use_tokens import SingleUseTokenIssuer, redeem

INVALID_TOKEN = "This confirmation link is no longer valid"  # noqa: S105


class EmailVerificationService:
    def __init__(
        self,
        users: UserRepositoryProtocol,
        tokens: SingleUseTokenRepositoryProtocol,
        mailer: AccountMailerProtocol,
        *,
        lifetime: timedelta,
        resend_cooldown: timedelta = timedelta(0),
    ) -> None:
        self._users = users
        self._tokens = SingleUseTokenIssuer(
            tokens,
            TokenPurpose.EMAIL_VERIFICATION,
            lifetime=lifetime,
            resend_cooldown=resend_cooldown,
        )
        self._mailer = mailer

    async def request(self, user: User) -> None:
        if user.email_verified_at is not None:
            return
        now = datetime.now(UTC)
        issued = await self._tokens.issue(user.id, now)
        if issued is None:
            return
        token, expires_at = issued
        await self._mailer.send_email_verification(user, token, expires_at)

    async def confirm(self, token: str) -> User:
        now = datetime.now(UTC)
        found = await redeem(self._tokens, self._users, token, now)
        if found is None:
            raise AuthError(INVALID_TOKEN, code=ErrorCode.AUTH_INVALID_TOKEN)

        stored, user = found
        await self._tokens.mark_used(stored, now)
        if user.email_verified_at is None:
            user.email_verified_at = now
            await self._users.save(user)
        return user
