from typing import Annotated

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import (
    Password,
    UserRead,
    reject_password_exceeding_bcrypt_input_limit,
)

SingleUseToken = Annotated[str, Field(min_length=1, max_length=200)]


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ImpersonationToken(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead
    impersonator: UserRead


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: SingleUseToken
    new_password: Password

    @field_validator("new_password")
    @classmethod
    def check_password_length_in_bytes(cls, value: str) -> str:
        return reject_password_exceeding_bcrypt_input_limit(value)


class EmailVerificationConfirm(BaseModel):
    token: SingleUseToken
