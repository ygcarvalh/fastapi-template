from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.request_log import CLIENT_IP_LENGTH, PATH_LENGTH, REQUEST_ID_LENGTH

SOURCE_LENGTH = 16
METHOD_LENGTH = 10
TABLE_NAME_LENGTH = 63
ACTION_LENGTH = 20
ROW_PK_LENGTH = 128


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_table_name_row_pk", "table_name", "row_pk"),
        Index("ix_audit_logs_actor_id_occurred_at", "actor_id", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    request_id: Mapped[str | None] = mapped_column(
        String(REQUEST_ID_LENGTH), default=None, index=True
    )
    actor_id: Mapped[int | None] = mapped_column(default=None)
    impersonator_id: Mapped[int | None] = mapped_column(default=None)
    source: Mapped[str] = mapped_column(String(SOURCE_LENGTH))
    method: Mapped[str | None] = mapped_column(String(METHOD_LENGTH), default=None)
    path: Mapped[str | None] = mapped_column(String(PATH_LENGTH), default=None)
    client_ip: Mapped[str | None] = mapped_column(
        String(CLIENT_IP_LENGTH), default=None
    )
    table_name: Mapped[str] = mapped_column(String(TABLE_NAME_LENGTH))
    action: Mapped[str] = mapped_column(String(ACTION_LENGTH))
    row_pk: Mapped[str | None] = mapped_column(String(ROW_PK_LENGTH), default=None)
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    truncated: Mapped[bool] = mapped_column(
        Boolean, server_default="false", default=False
    )
