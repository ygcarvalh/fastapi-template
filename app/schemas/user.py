from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

BCRYPT_MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8


class UserCreate(BaseModel):
    email: EmailStr
    password: Annotated[
        str,
        Field(min_length=MIN_PASSWORD_LENGTH, max_length=BCRYPT_MAX_PASSWORD_BYTES),
    ]

    @field_validator("password")
    @classmethod
    def reject_password_exceeding_bcrypt_input_limit(cls, value: str) -> str:
        if len(value.encode()) > BCRYPT_MAX_PASSWORD_BYTES:
            raise ValueError(
                f"password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes"
            )
        return value


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    created_at: datetime
