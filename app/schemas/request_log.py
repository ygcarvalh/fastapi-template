from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, computed_field

from app.core.observability.request_context import REQUEST_ID_REGEX
from app.models.request_log import PATH_LENGTH
from app.schemas.base import ORMModel
from app.schemas.pagination import CursorQuery

Outcome = Literal["success", "warning", "error"]

CLIENT_ERROR_STATUS = 400
SERVER_ERROR_STATUS = 500


def outcome_for(status_code: int) -> Outcome:
    if status_code >= SERVER_ERROR_STATUS:
        return "error"
    if status_code >= CLIENT_ERROR_STATUS:
        return "warning"
    return "success"


class RequestLogRead(ORMModel):
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
class RequestLogQuery(CursorQuery):
    outcome: Outcome | None = None
    method: Annotated[str, Field(pattern=r"^[A-Z]{3,10}$")] | None = None
    # A prefix, not a substring: a leading wildcard cannot use the index.
    path: Annotated[str, Field(max_length=PATH_LENGTH)] | None = None
    request_id: Annotated[str, Field(pattern=REQUEST_ID_REGEX)] | None = None
    user_id: int | None = None


class RequestRecord(BaseModel):
    request_id: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    client_ip: str | None = None
    user_id: int | None = None
