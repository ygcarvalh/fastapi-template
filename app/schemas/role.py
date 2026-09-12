from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.role import FEATURES_LENGTH, NAME_LENGTH, Role, Scope


class PermissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class RoleRead(BaseModel):
    id: int
    name: str
    features: str | None
    grants: list[GrantRead]


def to_role_read(role: Role) -> RoleRead:
    return RoleRead(
        id=role.id,
        name=role.name,
        features=role.features,
        grants=[
            GrantRead(
                resource=grant.permission.resource,
                action=grant.permission.action,
                scope=grant.scope,
            )
            for grant in role.grants
        ],
    )
