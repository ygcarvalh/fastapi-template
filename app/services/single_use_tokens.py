from datetime import UTC, datetime, timedelta

from app.core.security import hash_single_use_token, new_single_use_token
from app.models.single_use_token import SingleUseToken
from app.models.user import User
from app.services.protocols import (
    SingleUseTokenRepositoryProtocol,
    UserRepositoryProtocol,
)


def issued_within(token: SingleUseToken, now: datetime, cooldown: timedelta) -> bool:
    issued = token.created_at
    if issued is None:
        return False
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=UTC)
    return now - issued < cooldown


class SingleUseTokenIssuer:
    def __init__(
        self,
        repo: SingleUseTokenRepositoryProtocol,
        purpose: str,
        *,
        lifetime: timedelta,
        resend_cooldown: timedelta = timedelta(0),
    ) -> None:
        self._repo = repo
        self._purpose = purpose
        self._lifetime = lifetime
        self._resend_cooldown = resend_cooldown

    # A fresh token invalidates the ones before it, so a stolen link stops
    # working the moment its owner asks for another.
    async def issue(self, user_id: int, now: datetime) -> tuple[str, datetime] | None:
        if await self._sent_recently(user_id, now):
            return None
        await self._repo.revoke_all_for(user_id, self._purpose, now)
        token = new_single_use_token()
        expires_at = now + self._lifetime
        await self._repo.create(
            SingleUseToken(
                token_hash=hash_single_use_token(token),
                user_id=user_id,
                purpose=self._purpose,
                expires_at=expires_at,
            )
        )
        return token, expires_at

    async def active(self, token: str, now: datetime) -> SingleUseToken | None:
        return await self._repo.get_active(
            hash_single_use_token(token), self._purpose, now
        )

    async def mark_used(self, token: SingleUseToken, now: datetime) -> None:
        await self._repo.mark_used(token, now)

    async def revoke_all_for(self, user_id: int, now: datetime) -> int:
        return await self._repo.revoke_all_for(user_id, self._purpose, now)

    async def _sent_recently(self, user_id: int, now: datetime) -> bool:
        if not self._resend_cooldown:
            return False
        latest = await self._repo.latest_for(user_id, self._purpose)
        return latest is not None and issued_within(latest, now, self._resend_cooldown)


async def redeem(
    tokens: SingleUseTokenIssuer,
    users: UserRepositoryProtocol,
    token: str,
    now: datetime,
) -> tuple[SingleUseToken, User] | None:
    stored = await tokens.active(token, now)
    if stored is None:
        return None
    user = await users.get(stored.user_id)
    return None if user is None else (stored, user)
