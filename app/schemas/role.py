from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.role import FEATURES_LENGTH, NAME_LENGTH, Scope
from app.schemas.base import ORMModel


class PermissionRead(ORMModel):
    resource: str
    action: str


class GrantWrite(BaseModel):
    resource: str
    action: str
    scope: Scope = Scope.OWN


class RoleWrite(BaseModel):
    name: str = Field(min_length=1, max_length=NAME_LENGTH)
    grants: list[GrantWrite] = []
    features: str | None = Field(default=None, max_length=FEATURES_LENGTH)

    @field_validator("name")
    @classmethod
    def trim_the_name(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("name cannot be blank")
        return trimmed


class MemberAssignment(BaseModel):
    user_id: int


class GrantRead(BaseModel):
    resource: str
    action: str
    scope: Scope

    # A `RolePermission` carries its resource/action one level down, under
    # `.permission`, so a plain `from_attributes=True` read cannot see them:
    # this flattens the ORM shape into the flat one before validation, and
    # leaves an already-flat dict or `GrantRead` alone.
    @model_validator(mode="before")
    @classmethod
    def flatten_a_role_permission(cls, value: Any) -> Any:
        if isinstance(value, dict) or not hasattr(value, "permission"):
            return value
        return {
            "resource": value.permission.resource,
            "action": value.permission.action,
            "scope": value.scope,
        }


class RoleRead(ORMModel):
    id: int
    name: str
    features: str | None
    grants: list[GrantRead]
