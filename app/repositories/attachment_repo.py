from collections.abc import Sequence

from sqlalchemy import select

from app.models.attachment import Attachment
from app.models.item import Item
from app.repositories.base import CrudRepository


class AttachmentRepository(CrudRepository[Attachment]):
    _model = Attachment

    async def list_for_item(self, item_id: int) -> Sequence[Attachment]:
        return await self._all(
            select(Attachment)
            .where(Attachment.item_id == item_id)
            .order_by(Attachment.id)
        )

    async def get_for_owner(
        self, attachment_id: int, owner_id: int
    ) -> Attachment | None:
        return await self._one_or_none(
            select(Attachment)
            .join(Item, Item.id == Attachment.item_id)
            .where(
                Attachment.id == attachment_id,
                Item.owner_id == owner_id,
                Item.is_active(),
            )
        )
