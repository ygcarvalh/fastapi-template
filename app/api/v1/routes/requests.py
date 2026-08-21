from typing import Annotated

from fastapi import APIRouter, Path, Query

from app.api.deps import CurrentUser, RequestLogServiceDep, RequireAuth
from app.core.features import Feature, require_feature
from app.core.request_context import REQUEST_ID_REGEX
from app.schemas.error import AUTHENTICATED_ERROR_RESPONSES
from app.schemas.pagination import CursorPage
from app.schemas.request_log import RequestLogQuery, RequestLogRead

private_router = APIRouter(
    prefix="/requests",
    tags=["requests"],
    dependencies=[require_feature(Feature.REQUEST_LOG), RequireAuth],
    responses=AUTHENTICATED_ERROR_RESPONSES,
)


@private_router.get("")
async def list_requests(
    current_user: CurrentUser,
    service: RequestLogServiceDep,
    query: Annotated[RequestLogQuery, Query()],
) -> CursorPage[RequestLogRead]:
    entries, next_cursor = await service.list_for(current_user, query)
    return CursorPage(
        items=[RequestLogRead.model_validate(entry) for entry in entries],
        limit=query.limit,
        next_cursor=next_cursor,
    )


@private_router.get("/{request_id}")
async def get_request(
    request_id: Annotated[str, Path(pattern=REQUEST_ID_REGEX)],
    current_user: CurrentUser,
    service: RequestLogServiceDep,
) -> RequestLogRead:
    entry = await service.get_for(current_user, request_id)
    return RequestLogRead.model_validate(entry)
