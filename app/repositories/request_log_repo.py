from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import ColumnElement, CursorResult, delete, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.request_log import RequestLog
from app.schemas.request_log import (
    CLIENT_ERROR_STATUS,
    SERVER_ERROR_STATUS,
    RequestLogQuery,
    decode_cursor,
)

MAX_STATUS = 599

DELETE_BATCH_SIZE = 5000

OUTCOME_RANGES: dict[str, tuple[int, int]] = {
    "success": (0, CLIENT_ERROR_STATUS - 1),
    "warning": (CLIENT_ERROR_STATUS, SERVER_ERROR_STATUS - 1),
    "error": (SERVER_ERROR_STATUS, MAX_STATUS),
}


def _where(query: RequestLogQuery) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if query.user_id is not None:
        conditions.append(RequestLog.user_id == query.user_id)
    if query.outcome is not None:
        low, high = OUTCOME_RANGES[query.outcome]
        conditions.append(RequestLog.status_code.between(low, high))
    if query.method:
        conditions.append(RequestLog.method == query.method)
    if query.path:
        conditions.append(RequestLog.path.startswith(query.path, autoescape=True))
    if query.request_id:
        conditions.append(RequestLog.request_id == query.request_id)
    if query.since is not None:
        conditions.append(RequestLog.created_at >= query.since)
    if query.until is not None:
        conditions.append(RequestLog.created_at <= query.until)
    if query.cursor is not None:
        moment, entry_id = decode_cursor(query.cursor)
        # A row comparison, so PostgreSQL can walk the (created_at, id) order
        # instead of counting past rows the way an offset makes it.
        conditions.append(
            tuple_(RequestLog.created_at, RequestLog.id) < (moment, entry_id)
        )
    return conditions


class RequestLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, entry: RequestLog) -> RequestLog:
        self._session.add(entry)
        await self._session.flush()
        return entry

    # One row more than asked for, which is how the caller learns there is a
    # next page without anybody counting the whole table.
    async def list_page(self, query: RequestLogQuery) -> Sequence[RequestLog]:
        result = await self._session.execute(
            select(RequestLog)
            .where(*_where(query))
            # created_at alone is not a total order, and pagination with ties
            # repeats rows.
            .order_by(RequestLog.created_at.desc(), RequestLog.id.desc())
            .limit(query.limit + 1)
        )
        return result.scalars().all()

    # One statement per batch, so a retention run does not lock the table for
    # the length of a single enormous DELETE. The caller commits between calls.
    async def delete_batch_created_before(
        self, cutoff: datetime, batch_size: int = DELETE_BATCH_SIZE
    ) -> int:
        doomed = (
            select(RequestLog.id)
            .where(RequestLog.created_at < cutoff)
            .order_by(RequestLog.id)
            .limit(batch_size)
            .scalar_subquery()
        )
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                delete(RequestLog).where(RequestLog.id.in_(doomed))
            ),
        )
        return result.rowcount
