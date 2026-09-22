from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from app.core.error_codes import ErrorCode
from app.core.exceptions import NotFoundError
from app.models.role import Scope


def or_not_found[T](value: T | None, message: str, code: ErrorCode) -> T:
    if value is None:
        raise NotFoundError(message, code=code)
    return value


async def prune_before(
    delete_batch: Callable[[datetime, int], Awaitable[int]],
    retention: timedelta,
    batch_size: int,
) -> int:
    return await delete_batch(datetime.now(UTC) - retention, batch_size)


def scoped_to_owner[QueryT: BaseModel](
    query: QueryT, scope: Scope, owner_id: int, field: str
) -> QueryT:
    if scope == Scope.ALL:
        return query
    return query.model_copy(update={field: owner_id})
