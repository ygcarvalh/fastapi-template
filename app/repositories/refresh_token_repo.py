from datetime import datetime

from sqlalchemy import delete, select, update

from app.models.refresh_token import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository):
    async def create(self, token: RefreshToken) -> RefreshToken:
        return await self._insert(token)

    async def get_active(self, token_hash: str, now: datetime) -> RefreshToken | None:
        return await self._one_or_none(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )

    async def revoke(self, token_hash: str, now: datetime) -> int:
        return await self._affected(
            update(RefreshToken)
            .where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    async def revoke_all_for_user(self, user_id: int, now: datetime) -> int:
        return await self._affected(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def delete_expired(self, now: datetime) -> int:
        return await self._affected(
            delete(RefreshToken).where(RefreshToken.expires_at <= now)
        )
