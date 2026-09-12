from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.core.exceptions import NotFoundError
from app.models.request_log import RequestLog
from app.models.role import Scope
from app.models.user import User
from app.schemas.pagination import encode_cursor
from app.schemas.request_log import RequestLogQuery, RequestRecord
from app.services.protocols import RequestLogRepositoryProtocol


class RequestLogService:
    def __init__(self, repo: RequestLogRepositoryProtocol) -> None:
        self._repo = repo

    # Scoping silently rather than refusing keeps whose ids exist to ourselves.
    def _visible(
        self, viewer: User, scope: Scope, query: RequestLogQuery
    ) -> RequestLogQuery:
        if scope == Scope.ALL:
            return query
        return query.model_copy(update={"user_id": viewer.id})

    async def record(self, record: RequestRecord) -> RequestLog:
        return await self._repo.create(RequestLog(**record.model_dump()))

    async def list_for(
        self, viewer: User, scope: Scope, query: RequestLogQuery
    ) -> tuple[Sequence[RequestLog], str | None]:
        found = await self._repo.list_page(self._visible(viewer, scope, query))
        page = list(found[: query.limit])
        has_more = len(found) > query.limit
        cursor = (
            encode_cursor(page[-1].created_at, page[-1].id)
            if has_more and page
            else None
        )
        return page, cursor

    async def get_for(self, viewer: User, scope: Scope, request_id: str) -> RequestLog:
        scoped = self._visible(
            viewer, scope, RequestLogQuery(request_id=request_id, limit=1)
        )
        entry = next(iter(await self._repo.list_page(scoped)), None)
        if entry is None:
            raise NotFoundError("Request not found")
        return entry

    async def prune_batch(self, retention: timedelta, batch_size: int) -> int:
        return await self._repo.delete_batch_created_before(
            datetime.now(UTC) - retention, batch_size
        )
