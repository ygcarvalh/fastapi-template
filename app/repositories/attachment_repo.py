from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attachment import Attachment
from app.models.item import Item

ACTIVE_ITEM = Item.deleted_at.is_(None)


class AttachmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, attachment: Attachment) -> Attachment:
        self._session.add(attachment)
        await self._session.flush()
        await self._session.refresh(attachment)
        return attachment

    async def list_for_item(self, item_id: int) -> Sequence[Attachment]:
        result = await self._session.execute(
            select(Attachment)
            .where(Attachment.item_id == item_id)
            .order_by(Attachment.id)
        )
        return result.scalars().all()

    async def get_for_owner(
        self, attachment_id: int, owner_id: int
    ) -> Attachment | None:
        result = await self._session.execute(
            select(Attachment)
            .join(Item, Item.id == Attachment.item_id)
            .where(
                Attachment.id == attachment_id, Item.owner_id == owner_id, ACTIVE_ITEM
            )
        )
        return result.scalar_one_or_none()

    async def delete(self, attachment: Attachment) -> None:
        await self._session.delete(attachment)
        await self._session.flush()
