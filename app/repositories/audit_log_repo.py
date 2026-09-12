from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.schemas.audit_log import AuditLogQuery
from app.schemas.pagination import decode_cursor

DELETE_BATCH_SIZE = 5000


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
    if query.cursor is not None:
        moment, entry_id = decode_cursor(query.cursor)
        conditions.append(
            tuple_(AuditLog.occurred_at, AuditLog.id) < (moment, entry_id)
        )
    return conditions


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, entry: AuditLog) -> AuditLog:
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_page(self, query: AuditLogQuery) -> Sequence[AuditLog]:
        result = await self._session.execute(
            select(AuditLog)
            .where(*_where(query))
            .order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc())
            .limit(query.limit + 1)
        )
        return result.scalars().all()

    async def get(self, entry_id: int) -> AuditLog | None:
        return await self._session.get(AuditLog, entry_id)

    async def delete_batch_occurred_before(
        self, cutoff: datetime, batch_size: int = DELETE_BATCH_SIZE
    ) -> int:
        doomed = (
            select(AuditLog.id)
            .where(AuditLog.occurred_at < cutoff)
            .order_by(AuditLog.id)
            .limit(batch_size)
            .scalar_subquery()
        )
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                delete(AuditLog).where(AuditLog.id.in_(doomed))
            ),
        )
        return result.rowcount
