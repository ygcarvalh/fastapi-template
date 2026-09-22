from datetime import datetime

from sqlalchemy import delete, select, update

from app.models.single_use_token import SingleUseToken
from app.repositories.base import CrudRepository


class SingleUseTokenRepository(CrudRepository[SingleUseToken]):
    _model = SingleUseToken

    async def get_active(
        self, token_hash: str, purpose: str, now: datetime
    ) -> SingleUseToken | None:
        return await self._one_or_none(
            select(SingleUseToken).where(
                SingleUseToken.token_hash == token_hash,
                SingleUseToken.purpose == purpose,
                SingleUseToken.used_at.is_(None),
                SingleUseToken.expires_at > now,
            )
        )

    async def latest_for(self, user_id: int, purpose: str) -> SingleUseToken | None:
        return await self._first(
            select(SingleUseToken)
            .where(
                SingleUseToken.user_id == user_id,
                SingleUseToken.purpose == purpose,
            )
            .order_by(SingleUseToken.created_at.desc(), SingleUseToken.id.desc())
            .limit(1)
        )

    async def mark_used(self, token: SingleUseToken, now: datetime) -> None:
        token.used_at = now
        await self._flush()

    async def revoke_all_for(self, user_id: int, purpose: str, now: datetime) -> int:
        return await self._affected(
            update(SingleUseToken)
            .where(
                SingleUseToken.user_id == user_id,
                SingleUseToken.purpose == purpose,
                SingleUseToken.used_at.is_(None),
            )
            .values(used_at=now)
        )

    async def delete_expired(self, now: datetime) -> int:
        return await self._affected(
            delete(SingleUseToken).where(SingleUseToken.expires_at < now)
        )
