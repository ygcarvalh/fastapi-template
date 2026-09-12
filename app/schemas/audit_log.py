from datetime import datetime
from typing import Annotated, Any, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.core.audit.policy import AuditAction
from app.core.observability.request_context import REQUEST_ID_REGEX
from app.models.audit_log import ACTION_LENGTH, ROW_PK_LENGTH, TABLE_NAME_LENGTH
from app.schemas.pagination import CURSOR_REGEX, decode_cursor


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: datetime
    request_id: str | None
    actor_id: int | None
    impersonator_id: int | None
    source: str
    method: str | None
    path: str | None
    table_name: str
    action: str
    row_pk: str | None
    changes: dict[str, Any]
    truncated: bool


class AuditLogQuery(BaseModel):
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    cursor: Annotated[str, Field(pattern=CURSOR_REGEX)] | None = None
    actor_id: int | None = None
    impersonator_id: int | None = None
    table_name: Annotated[str, Field(max_length=TABLE_NAME_LENGTH)] | None = None
    row_pk: Annotated[str, Field(max_length=ROW_PK_LENGTH)] | None = None
    action: Annotated[str, Field(max_length=ACTION_LENGTH)] | None = None
    request_id: Annotated[str, Field(pattern=REQUEST_ID_REGEX)] | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None

    @field_validator("cursor")
    @classmethod
    def reject_a_cursor_we_did_not_issue(cls, value: str | None) -> str | None:
        if value is not None:
            decode_cursor(value)
        return value

    @field_validator("action")
    @classmethod
    def reject_an_action_the_trail_never_records(cls, value: str | None) -> str | None:
        if value is not None and value not in set(AuditAction):
            raise ValueError("action is not one this API records")
        return value

    @model_validator(mode="after")
    def reject_an_inverted_window(self) -> Self:
        if (
            self.since is not None
            and self.until is not None
            and self.since > self.until
        ):
            raise ValueError("since must not be later than until")
        return self


class AuditEvent(BaseModel):
    table_name: str
    action: AuditAction
    row_pk: str | None = None
    changes: dict[str, Any] = Field(default_factory=dict)
