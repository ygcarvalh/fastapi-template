from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, token: RefreshToken) -> RefreshToken:
        self._session.add(token)
        await self._session.flush()
        return token

    async def get_active(self, token_hash: str, now: datetime) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def revoke(self, token_hash: str, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.token_hash == token_hash,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            ),
        )
        return result.rowcount

    async def revoke_all_for_user(self, user_id: int, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
                )
                .values(revoked_at=now)
            ),
        )
        return result.rowcount

    async def delete_expired(self, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                delete(RefreshToken).where(RefreshToken.expires_at <= now)
            ),
        )
        return result.rowcount
