from datetime import UTC, datetime, timedelta

from app.core.error_codes import ErrorCode
from app.core.exceptions import AuthError
from app.core.security import hash_single_use_token, new_single_use_token
from app.models.single_use_token import SingleUseToken, TokenPurpose
from app.models.user import User
from app.services.protocols import (
    AccountMailerProtocol,
    SingleUseTokenRepositoryProtocol,
    UserRepositoryProtocol,
)
from app.services.single_use_tokens import issued_within

INVALID_TOKEN = "This confirmation link is no longer valid"


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
        self._tokens = tokens
        self._mailer = mailer
        self._lifetime = lifetime
        self._resend_cooldown = resend_cooldown

    async def request(self, user: User) -> None:
        if user.email_verified_at is not None:
            return
        now = datetime.now(UTC)
        if await self._sent_recently(user.id, now):
            return
        await self._tokens.revoke_all_for(user.id, TokenPurpose.EMAIL_VERIFICATION, now)
        token = new_single_use_token()
        expires_at = now + self._lifetime
        await self._tokens.create(
            SingleUseToken(
                token_hash=hash_single_use_token(token),
                user_id=user.id,
                purpose=TokenPurpose.EMAIL_VERIFICATION,
                expires_at=expires_at,
            )
        )
        await self._mailer.send_email_verification(user, token, expires_at)

    async def _sent_recently(self, user_id: int, now: datetime) -> bool:
        if not self._resend_cooldown:
            return False
        latest = await self._tokens.latest_for(user_id, TokenPurpose.EMAIL_VERIFICATION)
        return latest is not None and issued_within(latest, now, self._resend_cooldown)

    async def confirm(self, token: str) -> User:
        now = datetime.now(UTC)
        stored = await self._tokens.get_active(
            hash_single_use_token(token), TokenPurpose.EMAIL_VERIFICATION, now
        )
        if stored is None:
            raise AuthError(INVALID_TOKEN, code=ErrorCode.AUTH_INVALID_TOKEN)

        user = await self._users.get(stored.user_id)
        if user is None:
            raise AuthError(INVALID_TOKEN, code=ErrorCode.AUTH_INVALID_TOKEN)

        await self._tokens.mark_used(stored, now)
        if user.email_verified_at is None:
            user.email_verified_at = now
            await self._users.save(user)
        return user
