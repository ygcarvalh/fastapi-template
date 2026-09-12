from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from app.core.exceptions import NotFoundError
from app.models.audit_log import AuditLog
from app.models.role import Scope
from app.models.user import User
from app.schemas.audit_log import AuditLogQuery
from app.schemas.pagination import encode_cursor
from app.services.protocols import AuditLogRepositoryProtocol


class AuditLogService:
    def __init__(self, repo: AuditLogRepositoryProtocol) -> None:
        self._repo = repo

    def _visible(
        self, viewer: User, scope: Scope, query: AuditLogQuery
    ) -> AuditLogQuery:
        if scope == Scope.ALL:
            return query
        return query.model_copy(update={"actor_id": viewer.id})

    async def list_for(
        self, viewer: User, scope: Scope, query: AuditLogQuery
    ) -> tuple[Sequence[AuditLog], str | None]:
        found = await self._repo.list_page(self._visible(viewer, scope, query))
        page = list(found[: query.limit])
        has_more = len(found) > query.limit
        cursor = (
            encode_cursor(page[-1].occurred_at, page[-1].id)
            if has_more and page
            else None
        )
        return page, cursor

    async def get_for(self, viewer: User, scope: Scope, entry_id: int) -> AuditLog:
        entry = await self._repo.get(entry_id)
        if entry is None or (scope != Scope.ALL and entry.actor_id != viewer.id):
            raise NotFoundError("Audit entry not found")
        return entry

    async def prune_batch(self, retention: timedelta, batch_size: int) -> int:
        return await self._repo.delete_batch_occurred_before(
            datetime.now(UTC) - retention, batch_size
        )
