from typing import Any

from pydantic import BaseModel, Field


class ValidationDetail(BaseModel):
    type: str
    loc: list[str | int]
    msg: str
    ctx: dict[str, str | int] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    detail: str
    message: str
    code: str
    params: dict[str, str | int] = Field(default_factory=dict)
    request_id: str | None = None


class ValidationErrorResponse(BaseModel):
    detail: list[ValidationDetail]
    message: str
    code: str
    params: dict[str, str | int] = Field(default_factory=dict)
    request_id: str | None = None


COMMON_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    422: {"model": ValidationErrorResponse},
    429: {"model": ErrorResponse},
    500: {"model": ErrorResponse},
}

AUTHENTICATED_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
}
