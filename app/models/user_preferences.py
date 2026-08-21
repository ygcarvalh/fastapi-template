from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import TimestampMixin

LOCALE_LENGTH = 10
THEME_LENGTH = 10
FEATURES_LENGTH = 200

DEFAULT_LOCALE = "en-US"
DEFAULT_THEME = "system"


class UserPreferences(Base, TimestampMixin):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), unique=True, index=True
    )
    locale: Mapped[str] = mapped_column(
        String(LOCALE_LENGTH), default=DEFAULT_LOCALE, server_default=DEFAULT_LOCALE
    )
    theme: Mapped[str] = mapped_column(
        String(THEME_LENGTH), default=DEFAULT_THEME, server_default=DEFAULT_THEME
    )
    show_request_id: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    # NULL means "follow the environment". An empty string is a real answer:
    # this account has every optional feature turned off.
    features: Mapped[str | None] = mapped_column(String(FEATURES_LENGTH), default=None)
