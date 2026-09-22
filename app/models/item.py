from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import SoftDeleteMixin, TimestampMixin, VersionMixin

if TYPE_CHECKING:
    from app.models.attachment import Attachment
    from app.models.user import User


class Item(Base, TimestampMixin, SoftDeleteMixin, VersionMixin):
    __tablename__ = "items"
    __table_args__ = (Index("ix_items_owner_id_deleted_at", "owner_id", "deleted_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    owner: Mapped["User"] = relationship(back_populates="items")
    attachments: Mapped[list["Attachment"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )
