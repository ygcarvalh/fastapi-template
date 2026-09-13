from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

TOKEN_HASH_LENGTH = 64
PURPOSE_LENGTH = 30


class TokenPurpose(StrEnum):
    EMAIL_VERIFICATION = "email-verification"
    PASSWORD_RESET = "password-reset"


class SingleUseToken(Base):
    __tablename__ = "single_use_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(PURPOSE_LENGTH))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
