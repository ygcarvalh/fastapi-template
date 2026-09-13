from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.single_use_token import SingleUseToken


class SingleUseTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, token: SingleUseToken) -> SingleUseToken:
        self._session.add(token)
        await self._session.flush()
        await self._session.refresh(token)
        return token

    async def get_active(
        self, token_hash: str, purpose: str, now: datetime
    ) -> SingleUseToken | None:
        result = await self._session.execute(
            select(SingleUseToken).where(
                SingleUseToken.token_hash == token_hash,
                SingleUseToken.purpose == purpose,
                SingleUseToken.used_at.is_(None),
                SingleUseToken.expires_at > now,
            )
        )
        return result.scalar_one_or_none()

    async def mark_used(self, token: SingleUseToken, now: datetime) -> None:
        token.used_at = now
        await self._session.flush()

    async def revoke_all_for(self, user_id: int, purpose: str, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(SingleUseToken)
                .where(
                    SingleUseToken.user_id == user_id,
                    SingleUseToken.purpose == purpose,
                    SingleUseToken.used_at.is_(None),
                )
                .values(used_at=now)
            ),
        )
        return result.rowcount

    async def delete_expired(self, now: datetime) -> int:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                delete(SingleUseToken).where(SingleUseToken.expires_at < now)
            ),
        )
        return result.rowcount
