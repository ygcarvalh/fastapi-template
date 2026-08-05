from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


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


class ItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str | None
    owner_id: int
    created_at: datetime
    updated_at: datetime
