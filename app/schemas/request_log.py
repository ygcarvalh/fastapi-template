from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)

from app.core.observability.request_context import REQUEST_ID_REGEX
from app.models.request_log import PATH_LENGTH
from app.schemas.pagination import CURSOR_REGEX, decode_cursor

Outcome = Literal["success", "warning", "error"]

CLIENT_ERROR_STATUS = 400
SERVER_ERROR_STATUS = 500


def outcome_for(status_code: int) -> Outcome:
    if status_code >= SERVER_ERROR_STATUS:
        return "error"
    if status_code >= CLIENT_ERROR_STATUS:
        return "warning"
    return "success"


class RequestLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    request_id: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    client_ip: str | None
    user_id: int | None
    created_at: datetime

    # mypy does not model a decorator above @property.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def outcome(self) -> Outcome:
        return outcome_for(self.status_code)


# One model, because FastAPI explodes a single Pydantic model into query
# parameters per handler and a second one arrives as a scalar.
class RequestLogQuery(BaseModel):
    limit: Annotated[int, Field(ge=1, le=100)] = 20
    cursor: Annotated[str, Field(pattern=CURSOR_REGEX)] | None = None
    outcome: Outcome | None = None
    method: Annotated[str, Field(pattern=r"^[A-Z]{3,10}$")] | None = None
    # A prefix, not a substring: a leading wildcard cannot use the index.
    path: Annotated[str, Field(max_length=PATH_LENGTH)] | None = None
    request_id: Annotated[str, Field(pattern=REQUEST_ID_REGEX)] | None = None
    user_id: int | None = None
    since: AwareDatetime | None = None
    until: AwareDatetime | None = None

    @field_validator("cursor")
    @classmethod
    def reject_a_cursor_we_did_not_issue(cls, value: str | None) -> str | None:
        if value is not None:
            decode_cursor(value)
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


class RequestRecord(BaseModel):
    request_id: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    client_ip: str | None = None
    user_id: int | None = None
