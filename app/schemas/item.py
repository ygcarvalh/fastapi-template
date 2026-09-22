from datetime import datetime

from pydantic import BaseModel, field_validator

from app.schemas.base import ORMModel


class ItemCreate(BaseModel):
    title: str
    description: str | None = None


class ItemUpdate(BaseModel):
    title: str | None = None
    description: str | None = None

    @field_validator("title")
    @classmethod
    def reject_explicitly_null_title(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("title cannot be null")
        return value


class ItemRead(ORMModel):
    id: int
    title: str
    description: str | None
    owner_id: int
    version: int
    created_at: datetime
    updated_at: datetime
