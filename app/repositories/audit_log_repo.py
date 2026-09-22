from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import ColumnElement, select

from app.models.audit_log import AuditLog
from app.repositories.base import DELETE_BATCH_SIZE, BaseRepository
from app.repositories.cursor import cursor_condition
from app.schemas.audit_log import AuditLogQuery


def _where(query: AuditLogQuery) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if query.actor_id is not None:
        conditions.append(AuditLog.actor_id == query.actor_id)
    if query.impersonator_id is not None:
        conditions.append(AuditLog.impersonator_id == query.impersonator_id)
    if query.table_name:
        conditions.append(AuditLog.table_name == query.table_name)
    if query.row_pk:
        conditions.append(AuditLog.row_pk == query.row_pk)
    if query.action:
        conditions.append(AuditLog.action == query.action)
    if query.request_id:
        conditions.append(AuditLog.request_id == query.request_id)
    if query.since is not None:
        conditions.append(AuditLog.occurred_at >= query.since)
    if query.until is not None:
        conditions.append(AuditLog.occurred_at <= query.until)
    condition = cursor_condition(AuditLog.occurred_at, AuditLog.id, query.cursor)
    if condition is not None:
        conditions.append(condition)
    return conditions


class AuditLogRepository(BaseRepository):
    async def create(self, entry: AuditLog) -> AuditLog:
        return await self._insert(entry)

    async def list_page(self, query: AuditLogQuery) -> Sequence[AuditLog]:
        return await self._all(
            select(AuditLog)
            .where(*_where(query))
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
            .limit(query.limit + 1)
        )

    async def get(self, entry_id: int) -> AuditLog | None:
        return await self._session.get(AuditLog, entry_id)

    async def delete_batch_occurred_before(
        self, cutoff: datetime, batch_size: int = DELETE_BATCH_SIZE
    ) -> int:
        return await self._delete_batch_before(
            AuditLog.id, AuditLog.occurred_at, cutoff, batch_size
        )
