from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin

KEY_LENGTH = 64
FILENAME_LENGTH = 255
CONTENT_TYPE_LENGTH = 100

if TYPE_CHECKING:
    from app.models.item import Item


class Attachment(Base, TimestampMixin):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(KEY_LENGTH), unique=True)
    filename: Mapped[str] = mapped_column(String(FILENAME_LENGTH))
    content_type: Mapped[str] = mapped_column(String(CONTENT_TYPE_LENGTH))
    size_bytes: Mapped[int] = mapped_column(Integer)
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )

    item: Mapped["Item"] = relationship(back_populates="attachments")
