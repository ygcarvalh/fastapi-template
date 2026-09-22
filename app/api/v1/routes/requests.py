from typing import Annotated

from fastapi import Path, Query

from app.api.deps import CurrentUser, RequestLogServiceDep, require_permission
from app.api.v1.routing import protected_router
from app.core.authorization import READ, REQUEST_LOG
from app.core.features import Feature
from app.core.observability.request_context import REQUEST_ID_REGEX
from app.models.role import Scope
from app.schemas.pagination import CursorPage
from app.schemas.request_log import RequestLogQuery, RequestLogRead

private_router = protected_router(
    prefix="/requests", tags=["requests"], feature=Feature.REQUEST_LOG
)


@private_router.get("")
async def list_requests(
    current_user: CurrentUser,
    service: RequestLogServiceDep,
    query: Annotated[RequestLogQuery, Query()],
    scope: Annotated[Scope, require_permission(REQUEST_LOG, READ)],
) -> CursorPage[RequestLogRead]:
    entries, next_cursor = await service.list_for(current_user, scope, query)
    return CursorPage.of(
        entries,
        RequestLogRead.model_validate,
        limit=query.limit,
        next_cursor=next_cursor,
    )


@private_router.get("/{request_id}")
async def get_request(
    request_id: Annotated[str, Path(pattern=REQUEST_ID_REGEX)],
    current_user: CurrentUser,
    service: RequestLogServiceDep,
    scope: Annotated[Scope, require_permission(REQUEST_LOG, READ)],
) -> RequestLogRead:
    entry = await service.get_for(current_user, scope, request_id)
    return RequestLogRead.model_validate(entry)
