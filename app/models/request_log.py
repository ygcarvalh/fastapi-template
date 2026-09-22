from sqlalchemy import BigInteger, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.mixins import CreatedAtMixin

METHOD_LENGTH = 10
PATH_LENGTH = 512
CLIENT_IP_LENGTH = 45
REQUEST_ID_LENGTH = 64


class RequestLog(Base, CreatedAtMixin):
    __tablename__ = "request_logs"
    # The per-user listing always orders by time, so the pair is what serves it.
    __table_args__ = (
        Index("ix_request_logs_user_id_created_at", "user_id", "created_at"),
        Index("ix_request_logs_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
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
