from collections.abc import Iterable
from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.models.role import Role
from app.schemas.base import ORMModel

BCRYPT_MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8
NAME_MAX_LENGTH = 120


def normalize_email(value: str) -> str:
    return value.strip().lower()


def reject_password_exceeding_bcrypt_input_limit(value: str) -> str:
    if len(value.encode()) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError(f"password must be at most {BCRYPT_MAX_PASSWORD_BYTES} bytes")
    return value


# Every site that carries a password wants the byte-length check, so there is
# no bare, unchecked variant to keep around.
Password = Annotated[
    str,
    Field(min_length=MIN_PASSWORD_LENGTH, max_length=BCRYPT_MAX_PASSWORD_BYTES),
    AfterValidator(reject_password_exceeding_bcrypt_input_limit),
]
Name = Annotated[str, Field(max_length=NAME_MAX_LENGTH)]


class UserCreate(BaseModel):
    email: EmailStr
    password: Password
    name: Name | None = None

    @field_validator("email", mode="after")
    @classmethod
    def lowercase_email(cls, value: str) -> str:
        return normalize_email(value)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    name: Name | None = None

    @field_validator("email")
    @classmethod
    def reject_explicitly_null_email(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("email cannot be null")
        return normalize_email(value)

    @field_validator("name")
    @classmethod
    def reject_a_blank_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("name cannot be blank")
        return stripped


class PasswordChange(BaseModel):
    current_password: str
    new_password: Password

    @model_validator(mode="after")
    def reject_reusing_the_current_password(self) -> Self:
        if self.current_password == self.new_password:
            raise ValueError("new_password must differ from current_password")
        return self


class AccountDeactivate(BaseModel):
    password: str


class RoleAssignment(BaseModel):
    role: str


class UserRead(ORMModel):
    id: int
    email: EmailStr
    name: str | None
    roles: list[str]
    email_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_validator("roles", mode="before")
    @classmethod
    def read_the_role_names(cls, value: object) -> object:
        if not isinstance(value, Iterable) or isinstance(value, str):
            return value
        return [item.name if isinstance(item, Role) else item for item in value]
