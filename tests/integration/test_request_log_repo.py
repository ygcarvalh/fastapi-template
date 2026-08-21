from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.request_log import RequestLog
from app.repositories.request_log_repo import RequestLogRepository
from app.schemas.request_log import RequestLogQuery


async def _seed(
    session: AsyncSession, *, request_id: str, created_at: datetime
) -> None:
    session.add(
        RequestLog(
            request_id=request_id,
            method="GET",
            path="/api/v1/items",
            status_code=200,
            duration_ms=1.0,
            created_at=created_at,
        )
    )
    await session.flush()


async def test_the_window_narrows_the_page(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    await _seed(db_session, request_id="old", created_at=now - timedelta(days=2))
    await _seed(db_session, request_id="new", created_at=now)
    repo = RequestLogRepository(db_session)

    recent = await repo.list_page(
        RequestLogQuery(since=now - timedelta(hours=1), until=now + timedelta(hours=1))
    )

    assert [entry.request_id for entry in recent] == ["new"]


async def test_rows_older_than_the_cutoff_are_deleted(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    await _seed(db_session, request_id="old", created_at=now - timedelta(days=40))
    await _seed(db_session, request_id="new", created_at=now)
    repo = RequestLogRepository(db_session)

    removed = await repo.delete_batch_created_before(now - timedelta(days=30), 10)

    assert removed == 1
    assert [entry.request_id for entry in await repo.list_page(RequestLogQuery())] == [
        "new"
    ]
