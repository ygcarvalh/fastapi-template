from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.core.exceptions import NotFoundError
from app.models.request_log import RequestLog
from app.models.user import User, UserRole
from app.schemas.request_log import RequestLogQuery, RequestRecord
from app.services.protocols import RequestLogRepositoryProtocol


class RequestLogService:
    def __init__(self, repo: RequestLogRepositoryProtocol) -> None:
        self._repo = repo

    # An admin reads every row; anyone else is scoped to their own. Scoping
    # silently rather than refusing keeps whose ids exist to ourselves.
    def _visible(self, viewer: User, query: RequestLogQuery) -> RequestLogQuery:
        if viewer.role == UserRole.ADMIN:
            return query
        return query.model_copy(update={"user_id": viewer.id})

    async def record(self, record: RequestRecord) -> RequestLog:
        return await self._repo.create(RequestLog(**record.model_dump()))

    async def list_for(
        self, viewer: User, query: RequestLogQuery
    ) -> tuple[Sequence[RequestLog], int]:
        scoped = self._visible(viewer, query)
        entries = await self._repo.list_page(scoped)
        total = await self._repo.count(scoped)
        return entries, total

    async def get_for(self, viewer: User, request_id: str) -> RequestLog:
        scoped = self._visible(viewer, RequestLogQuery(request_id=request_id, limit=1))
        entry = next(iter(await self._repo.list_page(scoped)), None)
        if entry is None:
            raise NotFoundError("Request not found")
        return entry

    async def prune_batch(self, retention: timedelta, batch_size: int) -> int:
        return await self._repo.delete_batch_created_before(
            datetime.now(UTC) - retention, batch_size
        )
