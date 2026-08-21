from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

METHOD_LENGTH = 10
PATH_LENGTH = 512
CLIENT_IP_LENGTH = 45
REQUEST_ID_LENGTH = 64


class RequestLog(Base):
    __tablename__ = "request_logs"
    # The per-user listing always orders by time, so the pair is what serves it.
    __table_args__ = (
        Index("ix_request_logs_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(REQUEST_ID_LENGTH), index=True)
    method: Mapped[str] = mapped_column(String(METHOD_LENGTH))
    path: Mapped[str] = mapped_column(String(PATH_LENGTH))
    status_code: Mapped[int] = mapped_column()
    duration_ms: Mapped[float] = mapped_column(Float)
    client_ip: Mapped[str | None] = mapped_column(
        String(CLIENT_IP_LENGTH), default=None
    )
    # No foreign key: the trail outlives the account it describes, and the
    # writer commits on its own connection.
    user_id: Mapped[int | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
