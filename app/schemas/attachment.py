from datetime import datetime

from app.schemas.base import ORMModel


class AttachmentRead(ORMModel):
    id: int
    filename: str
    content_type: str
    size_bytes: int
    item_id: int
    created_at: datetime
