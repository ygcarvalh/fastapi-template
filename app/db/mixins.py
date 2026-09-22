from datetime import UTC, datetime
from typing import Any

from sqlalchemy import ColumnElement, DateTime, Integer, func, text
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    @classmethod
    def is_active(cls) -> ColumnElement[bool]:
        return cls.deleted_at.is_(None)

    def mark_deleted(self) -> None:
        self.deleted_at = datetime.now(UTC)


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TimestampMixin(CreatedAtMixin):
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class VersionMixin:
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"))

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        return {"version_id_col": cls.version}
