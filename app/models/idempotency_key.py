from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

KEY_LENGTH = 255
METHOD_LENGTH = 10
PATH_LENGTH = 255
HASH_LENGTH = 64
CONTENT_TYPE_LENGTH = 100


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_idempotency_keys_user_id_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(KEY_LENGTH))
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    method: Mapped[str] = mapped_column(String(METHOD_LENGTH))
    path: Mapped[str] = mapped_column(String(PATH_LENGTH))
    request_hash: Mapped[str] = mapped_column(String(HASH_LENGTH))
    status_code: Mapped[int | None] = mapped_column(Integer, default=None)
    response_body: Mapped[str | None] = mapped_column(Text, default=None)
    content_type: Mapped[str | None] = mapped_column(
        String(CONTENT_TYPE_LENGTH), default=None
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
