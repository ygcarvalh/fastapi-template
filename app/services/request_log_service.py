from collections.abc import Sequence
from datetime import timedelta

from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.models.request_log import RequestLog
from app.models.role import Scope
from app.models.user import User
from app.schemas.pagination import cursor_slice
from app.schemas.request_log import RequestLogQuery, RequestRecord
from app.services.protocols import RequestLogRepositoryProtocol
from app.services.support import prune_before, scoped_to_owner


class RequestLogService:
    def __init__(self, repo: RequestLogRepositoryProtocol) -> None:
        self._repo = repo

    # Scoping silently rather than refusing keeps whose ids exist to ourselves.
    def _visible(
        self, viewer: User, scope: Scope, query: RequestLogQuery
    ) -> RequestLogQuery:
        return scoped_to_owner(query, scope, viewer.id, "user_id")

    async def record(self, record: RequestRecord) -> RequestLog:
        return await self._repo.create(RequestLog(**record.model_dump()))

    async def list_for(
        self, viewer: User, scope: Scope, query: RequestLogQuery
    ) -> tuple[Sequence[RequestLog], str | None]:
        found = await self._repo.list_page(self._visible(viewer, scope, query))
        return cursor_slice(found, query.limit, lambda entry: entry.created_at)

    async def get_for(self, viewer: User, scope: Scope, request_id: str) -> RequestLog:
        scoped = self._visible(
            viewer, scope, RequestLogQuery(request_id=request_id, limit=1)
        )
        entry = next(iter(await self._repo.list_page(scoped)), None)
        if entry is None:
            raise NotFoundError(
                "Request not found", code=ErrorCode.REQUEST_LOG_NOT_FOUND
            )
        return entry

    async def prune_batch(self, retention: timedelta, batch_size: int) -> int:
        return await prune_before(
            self._repo.delete_batch_created_before, retention, batch_size
        )
