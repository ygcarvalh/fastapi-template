from collections.abc import Sequence
from datetime import timedelta

from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.models.audit_log import AuditLog
from app.models.role import Scope
from app.models.user import User
from app.schemas.audit_log import AuditLogQuery
from app.schemas.pagination import cursor_slice
from app.services.protocols import AuditLogRepositoryProtocol
from app.services.support import prune_before, scoped_to_owner


class AuditLogService:
    def __init__(self, repo: AuditLogRepositoryProtocol) -> None:
        self._repo = repo

    def _visible(
        self, viewer: User, scope: Scope, query: AuditLogQuery
    ) -> AuditLogQuery:
        return scoped_to_owner(query, scope, viewer.id, "actor_id")

    async def list_for(
        self, viewer: User, scope: Scope, query: AuditLogQuery
    ) -> tuple[Sequence[AuditLog], str | None]:
        found = await self._repo.list_page(self._visible(viewer, scope, query))
        return cursor_slice(found, query.limit, lambda entry: entry.occurred_at)

    async def get_for(self, viewer: User, scope: Scope, entry_id: int) -> AuditLog:
        entry = await self._repo.get(entry_id)
        if entry is None or (scope != Scope.ALL and entry.actor_id != viewer.id):
            raise NotFoundError(
                "Audit entry not found", code=ErrorCode.AUDIT_LOG_NOT_FOUND
            )
        return entry

    async def prune_batch(self, retention: timedelta, batch_size: int) -> int:
        return await prune_before(
            self._repo.delete_batch_occurred_before, retention, batch_size
        )
